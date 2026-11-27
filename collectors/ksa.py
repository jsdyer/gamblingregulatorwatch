"""Read the public Kansspelwijzer API and verify the adjudication text used by our reviewed case selection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from lxml import html
from public_register_io import arguments, download, write_output

BASE = "https://kansspelautoriteit.nl"
API = BASE + "/api/gambling-providers"
REGISTER = BASE + "/kansspelwijzer"
DECISIONS = BASE + "/sanctiebesluiten"


def page_digest(page):
    article = html.fromstring(page).xpath('//main')
    if len(article)!=1:
        raise ValueError("KSA source layout changed")
    text = " ".join(article[0].text_content().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect(args):
    rows=json.loads(download(API,args.cache))
    if not isinstance(rows,list) or not rows:
        raise ValueError("Empty or unexpected Kansspelwijzer register")
    ids=set(); terms=[]
    today=args.as_of.isoformat()
    for r in rows:
        if (r["id"] in ids or not r["company_name"] or not r["license_number"]
                or urlparse(r["detail_url"]).hostname!="kansspelautoriteit.nl"):
            raise ValueError("Unrecognised KSA licence record")
        ids.add(r["id"])
        start=date.fromisoformat(r["license_start_date"])
        end=date.fromisoformat(r["license_end_date"]) if r.get("license_end_date") else None
        active=start<=args.as_of and (not end or args.as_of<end)
        scope="; ".join(x for x in (r["game_type"], ", ".join(r.get("license_types") or [])) if x)
        data=dict(entity=r["company_name"],status="Listed; within published term" if active else "Listed; outside published term",
                  licence_id=str(r["license_number"]),record_id=str(r["id"]),date=today,date_basis="Official register observed; published licence term checked",
                  start_date=start.isoformat(),url=r["detail_url"],scope=scope or "Register does not specify activity",
                  active=active,eligible=active)
        # A machine owner can rent equipment to a separately licensed public venue.
        # That KSA permission alone does not establish a consumer operator.
        data["operator_licence"] = (
            r["game_type"] in {"Online gokspel", "Loterij", "Traditionele weddenschap"}
            or "Speelcasino" in (r.get("license_types") or [])
        )
        if end: data["end_date"]=end.isoformat()
        if r.get("brand_names"): data["trading_names"]=r["brand_names"]
        if (r.get("publication_link") or {}).get("uri"): data["decision_url"]=r["publication_link"]["uri"]
        terms.append(data)
    review=json.loads(Path(__file__).with_name("ksa-reviewed.json").read_text())
    def check(item):
        u,expected=item
        if page_digest(download(u,args.cache))!=expected:
            raise ValueError("KSA decision text changed. Check amounts, objections and appeal outcomes before republishing: "+u)
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(check,review["receipts"].items()))
    actions=review["actions"]
    if len({r["id"] for r in actions})!=len(actions) or any(r["url"] not in review["receipts"] for r in actions):
        raise ValueError("Inconsistent KSA receipts")
    return dict(id="ksa",name="Kansspelautoriteit",jurisdiction="Netherlands",role="Gambling licensing and enforcement regulator",
                register_url=REGISTER,enforcement_url=DECISIONS,checked_at=today,observed_at=today,
                coverage=(f"Full Kansspelwijzer provider feed, {len(terms):,} published permission rows across the online, "
                          "land-based and lottery categories. Licence numbers, scopes, validity dates and holder names come directly "
                          "from the register. Contact details are excluded. The enforcement collection is a reviewed selection of "
                          f"{len({r['case_id'] for r in actions})} named proceedings, including dated stages of objections and court review. "
                          "It is not a complete incident register and cannot support a national enforcement rate. "
                          "Contingent payments under compliance orders are distinct from fines."),
                licences=sorted(terms,key=lambda r:(r["entity"],r["licence_id"])),
                actions=sorted(actions,key=lambda r:(r["date"],r["id"]),reverse=True))


if __name__=="__main__":
    args=arguments()
    write_output(collect(args),args.output)
