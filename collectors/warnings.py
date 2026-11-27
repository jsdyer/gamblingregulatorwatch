"""Extract exact URLs and dated claims from the two regulator lists."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import json
import re
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "tobique": "https://thetgc.ca/unlicensed-sites/",
    "mga": "https://www.mga.org.mt/player-hub/unauthorised-urls/",
}


def domain(value):
    u = urlsplit(value if "://" in value else "//"+value)
    host = (u.hostname or "").lower().rstrip(".").removeprefix("www.").encode("idna").decode()
    if not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z0-9-]+",host):
        raise ValueError("Invalid published domain: "+value)
    return host


def extract(content, regulator):
    doc = html.fromstring(content)
    rows = []
    if regulator == "tobique":
        for panel, status in (("tab-1-panel","Current list"),("tab-2-panel","Previous list")):
            table, = doc.xpath('//*[@id=$id]//table', id=panel)
            for tr in table.xpath('.//tr[td and not(td/strong)]'):
                cells = tr.xpath('./td')
                value = cells[0].text_content().strip()
                date = datetime.strptime(cells[1].text_content().strip(), "%B %d, %Y").date()
                pdfs = tr.xpath('.//a/@href')
                report = next((u for u in pdfs if u.startswith("https://thetgc.ca/wp-content/")), SOURCES[regulator])
                rows.append((value,date,status,report))
    else:
        for div in doc.xpath('//div[./div/div[normalize-space()="URL"] and ./div/div[normalize-space()="Notice Date"] and ./div/div[@class="font-medium"]]'):
            value = div.xpath('./div[1]/div[2]')[0].text_content().strip()
            date = datetime.strptime(div.xpath('./div[2]/div[2]')[0].text_content().strip(),"%d/%m/%Y").date()
            rows.append((value,date,"Published notice",SOURCES[regulator]))
    if not rows:
        raise ValueError("Empty warning list from "+regulator)
    return [{"host":domain(v),"published_as":v,"date":d.isoformat(),"status":s,"evidence":u}
            for v,d,s,u in sorted(set(rows), key=lambda r:(r[1],r[0]), reverse=True)]


def refresh():
    path = ROOT/"sources/warnings.json"
    edition = json.loads(path.read_text()) if path.exists() else {}
    failures = []
    for rid, url in SOURCES.items():
        try:
            req = Request(url, headers={"User-Agent":"CoolCode regulatory record index (+https://coolcode.ca/)"})
            with urlopen(req,timeout=45) as response:
                items = extract(response.read(), rid)
            edition[rid] = {"source":url,"checked_at":datetime.now(timezone.utc).date().isoformat(),"items":items}
        except Exception as err:
            print(f"Retained {rid} warnings: {err}")
            failures.append(rid)
    if set(edition) != set(SOURCES):
        raise ValueError("A verified first edition is required for both lists")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(edition,ensure_ascii=False,indent=2)+"\n")
    tmp.replace(path)
    return failures


if __name__ == "__main__":
    raise SystemExit(bool(refresh()))
