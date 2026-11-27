"""Discover links to official notices. The queue never creates an enforcement case."""
import argparse
from datetime import date, datetime, timezone
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from lxml import etree, html

if __package__:
    from .public_register_io import write_output
else:
    from public_register_io import write_output

ROOT = Path(__file__).resolve().parents[1]
PER_PAGE = 100


def official_url(source, url, base=None):
    absolute = urljoin(base or source["index_url"], url)
    parts = urlsplit(absolute)
    if parts.scheme != "https" or parts.netloc.lower() != urlsplit(source["index_url"]).netloc.lower():
        raise ValueError("Unexpected publication host")
    return absolute


def fetch(url):
    request = Request(url, headers={"User-Agent": "CoolCode public-notice index (+https://coolcode.ca/)"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=35) as response:
                if urlsplit(response.geturl()).netloc.lower() != urlsplit(url).netloc.lower():
                    raise ValueError("Unexpected index redirect")
                return response.read(), response.headers
        except HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt:
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise
        sleep(1)


def candidate(source, title, href, published, basis, **extra):
    title = " ".join(title.split())
    url = official_url(source, href)
    if not title or not href or not urlsplit(url).path.startswith(source.get("url_prefix", "/")):
        raise ValueError("Invalid notice title or permalink")
    if published:
        published = date.fromisoformat(published).isoformat()
    return {"regulator": source["regulator"], "url": url, "title": title,
            "published_on": published, "date_basis": basis, **extra}


def wordpress(source, get):
    records = []
    page = 1
    total = None
    while True:
        query = {"per_page": PER_PAGE, "page": page, "orderby": "id", "order": "desc",
                 "_fields": "id,link,title,date,modified_gmt"}
        if "category" in source:
            query["categories"] = source["category"]
        url = official_url(source, source["endpoint"]) + "?" + urlencode(query)
        raw, headers = get(url)
        pages, advertised = int(headers["X-WP-TotalPages"]), int(headers["X-WP-Total"])
        if total is None:
            total = advertised
        if total <= 0 or total != advertised or pages != (total + PER_PAGE - 1) // PER_PAGE:
            raise ValueError("Inconsistent WordPress pagination totals")
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) != min(PER_PAGE, total - (page - 1) * PER_PAGE):
            raise ValueError("Incomplete WordPress page")
        for row in rows:
            # WP titles can contain HTML markup and numeric character references.
            title = html.fragment_fromstring(row["title"]["rendered"], create_parent=True).text_content()
            published = row["date"][:10]
            basis = "Publisher’s post date"
            if source.get("date_from_title"):
                match = re.match(r"^\s*(\d{1,2}/\d{1,2}/\d{4})(?:\s+|$)", title)
                published = datetime.strptime(match[1], "%d/%m/%Y").date().isoformat() if match else None
                basis = "Date printed in notice title" if match else "No date printed in notice title"
            modified = row.get("modified_gmt")
            if modified:
                datetime.fromisoformat(modified)
            records.append(candidate(source, title, row["link"], published, basis,
                                     source_modified_at=modified + "Z" if modified else None))
        if page == pages:
            return records
        page += 1


def ontario(source, get):
    url = source["index_url"]
    visited = set()
    expected_pages = None
    records = []
    while url:
        if url in visited:
            raise ValueError("Ontario pagination repeated a page")
        visited.add(url)
        raw, _ = get(url)
        # Explicit UTF-8 avoids misdecoding smart quotes when Drupal omits an HTTP charset.
        tree = html.fromstring(raw, parser=html.HTMLParser(encoding="utf-8"))
        views = tree.xpath("//*[contains(concat(' ',normalize-space(@class),' '),' view-id-search_news ')]")
        if len(views) != 1:
            raise ValueError("Ontario sector news view missing")
        cards = views[0].xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' view-content ')]/div")
        if not cards:
            raise ValueError("Ontario sector news cards missing")
        for card in cards:
            links = card.xpath(".//h5/a[@href]")
            dates = card.xpath(".//time/@datetime")
            tags = [n.text_content().strip() for n in card.xpath(".//*[@data-component-id='agco:badge']")]
            if len(links) != 1 or len(dates) != 1 or "Lottery and Gaming" not in tags:
                raise ValueError("Ontario sector news card changed")
            records.append(candidate(source, links[0].text_content(), links[0].get("href"),
                                     dates[0][:10], "Publisher’s news date"))
        if len(visited) == 1:
            last_links = views[0].xpath(".//*[contains(@class,'pager__item--last')]/a/@href")
            expected_pages = (int(parse_qs(urlsplit(last_links[0]).query)["page"][0]) + 1
                              if last_links else 1)
        following = views[0].xpath(".//a[@rel='next']/@href")
        if bool(following) != (len(visited) < expected_pages) or len(following) > 1:
            raise ValueError("Ambiguous Ontario pagination")
        url = official_url(source, following[0], url) if following else None
        if url and urlsplit(url).path != urlsplit(source["index_url"]).path:
            raise ValueError("Ontario pagination left the sector index")
    return records


def scan(source, get):
    all_rows = {"wordpress": wordpress, "agco": ontario}[source["parser"]](source, get)
    if not all_rows or len({row["url"] for row in all_rows}) != len(all_rows):
        raise ValueError("Empty or overlapping official index pages")
    include = re.compile(source.get("include", ""), re.I)
    exclude = re.compile(source["exclude"], re.I) if source.get("exclude") else None
    selected = [row for row in all_rows if include.search(row["title"])
                and not (exclude and exclude.search(row["title"]))]
    return selected, len(all_rows)


def reviewed_sources(source, data_dir):
    cases = json.loads((data_dir / (source["regulator"] + ".json")).read_text())["actions"]
    result = {}
    valid = {case["id"] for case in cases}
    for case in cases:
        for key in ("url", "start_url"):
            if case.get(key):
                result.setdefault(case[key], set()).add(case["id"])
    for url, action_id in source.get("review_links", {}).items():
        if action_id not in valid:
            raise ValueError("Reviewed alternate link references an unknown case")
        result.setdefault(official_url(source, url), set()).add(action_id)
    return {url: sorted(ids) for url, ids in result.items()}


def refresh(config, previous, data_dir, as_of, get=fetch):
    old_sources = {s["regulator"]: s for s in previous.get("sources", [])}
    old_rows = previous.get("notices", [])
    sources, notices = [], []
    for source in config:
        rid = source["regulator"]
        last = old_sources.get(rid, {})
        prior = {r["url"]: dict(r) for r in old_rows if r["regulator"] == rid}
        state = {k: source[k] for k in ("regulator", "name", "index_url", "coverage")}
        state.update(availability="manual", checked_at=as_of,
                     last_success_at=last.get("last_success_at"),
                     index_entries=last.get("index_entries"))
        if source["parser"] == "manual":
            state["status"] = "Manual checks only."
        else:
            try:
                found, entries = scan(source, get)
                reviewed = reviewed_sources(source, data_dir)
            except (OSError, HTTPException, etree.LxmlError, ValueError, TypeError, KeyError, IndexError) as exc:
                state.update(availability="unavailable",
                             status=f"Index check failed. Earlier links retained. {type(exc).__name__}: {exc}")
            else:
                present = {r["url"] for r in found}
                for row in prior.values():
                    row["listed"] = row["url"] in present
                    row["is_new"] = False
                    row["is_updated"] = False
                for row in found:
                    url = row["url"]
                    earlier = prior.get(url, {})
                    changed = bool(earlier and any(earlier.get(k) != row.get(k)
                                   for k in ("title", "published_on", "source_modified_at")))
                    row.update(first_seen=earlier.get("first_seen", as_of), last_seen=as_of, listed=True,
                               is_new=not earlier and bool(last.get("last_success_at")), is_updated=changed)
                    if changed or earlier.get("last_change_seen"):
                        row["last_change_seen"] = as_of if changed else earlier["last_change_seen"]
                    prior[url] = row
                for row in prior.values():
                    action_ids = reviewed.get(row["url"], [])
                    row.update(reviewed=bool(action_ids), reviewed_action_ids=action_ids)
                state.update(availability="available", status="All index pages checked.",
                             last_success_at=as_of, index_entries=entries)
        state["listed_count"] = sum(r["listed"] for r in prior.values())
        sources.append(state)
        notices.extend(prior.values())
    notices.sort(key=lambda n: (n["published_on"] or "", n["url"]), reverse=True)
    return {"checked_at": as_of, "sources": sources, "notices": notices}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=ROOT / "config/notice_indexes.json")
    p.add_argument("--source-dir", type=Path, default=ROOT / "sources")
    p.add_argument("--output", type=Path, default=ROOT / "sources/notice-index.json")
    p.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = p.parse_args()
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    edition = refresh(json.loads(args.config.read_text()), previous, args.source_dir, args.as_of.isoformat())
    write_output(edition, args.output)
    for src in edition["sources"]:
        print(f'{src["regulator"]}: {src["availability"]} ({src["listed_count"]} links) {src["status"]}')
    return int(any(src["availability"] == "unavailable" for src in edition["sources"]))


if __name__ == "__main__":
    sys.exit(main())
