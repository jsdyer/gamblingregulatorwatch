"""Build the Great Britain snapshot from the Commission's published CSVs and business decisions."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import StringIO
import csv
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from lxml import html
from public_register_io import arguments, download, write_output

BASE = "https://www.gamblingcommission.gov.uk"
REG = BASE + "/public-register/businesses/download"
INDEX = BASE + "/public-register/regulatory-actions/full"
CSV = BASE + "/downloads/business-licence-register-%s.csv"
APOLLO = BASE + "/public-register/business/detail/trading-names/38620"
APOLLO_ACTIONS = BASE + "/public-register/business/detail/actions/38620"
CONSUMER_ACTIVITIES = {
    "Society Lottery", "Bingo", "Casino", "Casino 1968 Act", "Casino 2005 Act", "Pool Betting",
    "Betting Intermediary", "General Betting Limited", "General Betting Standard",
    "General Betting Standard - Real Event", "General Betting Standard - Virtual Event",
    "General Betting Standard - No Gaming Machines", "Gaming Machine General Adult Gaming Centre",
    "Gaming Machine General Family Entertainment Centre",
}


def norm(text):
    return " ".join(text.split())


def collect(args):
    fetch = lambda url: download(url, args.cache)
    read = lambda kind: list(csv.DictReader(StringIO(fetch(CSV % kind).decode("utf-8-sig"))))
    accounts = {r["Account Number"]: r["Licence Account Name"] for r in read("businesses")}
    activity_rows = read("licences")
    checked = args.as_of.isoformat()
    groups = defaultdict(set)
    for row in activity_rows:
        group = tuple(row[k] for k in ("Account Number", "Licence Number", "Status", "Type", "Start Date", "End Date"))
        if group[0] not in accounts or not group[1] or not group[2]:
            raise ValueError("Inconsistent operating licence/holder export")
        groups[group].add(row["Activity"])
    licences = []
    for (account, licence, status, typ, start, end), activities in sorted(groups.items()):
        url = BASE + "/public-register/business/detail/" + account
        row = dict(entity=accounts[account], licence_id=licence, account_id=account, status=status,
                   date=(start[:10] or checked), date_basis="Activity start date in register" if start else "Register observed",
                   scope=typ + " — " + ", ".join(sorted(activities)), url=url, eligible=status == "Active")
        row["active"] = status=="Active"
        row["operator_licence"] = bool(activities & CONSUMER_ACTIVITIES)
        if row["active"]:
            row.update(date=checked,date_basis="Active activity observed in official register")
        if start: row["start_date"] = start[:10]
        if end: row["end_date"] = end[:10]
        if account == "38620": row["trading_names_url"] = APOLLO
        licences.append(row)
    doc = html.fromstring(fetch(INDEX))
    items = doc.xpath('//ol[@id="search-results"]/li')
    if not items or doc.xpath('//a[@rel="next"]'):
        raise ValueError("Unexpected register layout; review complete enumeration")
    def decision(li):
        a, = li.xpath('./a')
        entity = norm(a.text_content())
        url = urljoin(BASE, a.get("href"))
        slug = url.rsplit("/", 1)[-1]
        kind = norm(li.xpath("string(./strong)"))
        values = [norm(p.text_content()).split(":", 1)[-1].strip() for p in li.xpath("./p")]
        day = datetime.strptime(values[0], "%d %B %Y").date().isoformat()
        outcomes = values[1]
        doc = html.fromstring(fetch(url))
        details = norm(doc.xpath('string(//main)')).partition("Details")[2].partition("Related information")[0]
        account = norm(doc.xpath('string((//main//a[contains(@href,"/public-register/business/detail/")])[1])'))
        # Personal licence decisions also link to /business/detail/ in the source. The
        # holder CSV distinguishes operating accounts; the decision text rules out PML/PFL.
        if re.search(r'personal (management|functional|licence)|\bPML\b|\bPFL\b', details, re.I):
            return None
        if account not in accounts and not re.search(r'operating licen[cs]e', details, re.I):
            raise ValueError(f"Unclassified account on {url}; review before replacing the snapshot")
        if "appeal" in details.lower():
            raise ValueError(f"Review appellate status on {url} before counting this decision")
        key = 'ukgc-'+slug
        action = dict(id=key, case_id=key, entity=entity, date=day, date_basis="Commission decision date",
                      title=f"{kind} — {outcomes}", type="Settlement" if kind=="Settlement" else ("Revocation" if outcomes=="Revoked" else "Sanction"),
                      status="Settlement agreed" if kind=="Settlement" else "Commission decision issued",
                      url=url, summary=f"Recorded UK Gambling Commission outcome: {outcomes}.",
                      account_id=account, eligible=True, foreign_penalty=kind=="Sanction" and "Financial penalty" in outcomes)
        if action["foreign_penalty"]:
            # Use a single expressly named penalty. Two published orders explicitly reduce
            # the initially calculated amount; use that operative figure when shown.
            money = r"£([0-9][\d,]*(?:\.\d{2})?)"
            figures = re.findall(money, details)
            proposed = re.findall(r"financial penalty of " + money, details, re.I)
            reduced = re.findall(r"the quantum was reduced to " + money, details, re.I)
            if len(proposed) == 1 and (figures == proposed or (reduced and figures == proposed + reduced)):
                value = (reduced or proposed)[0].replace(",", "")
                action.update(amount=float(value) if "." in value else int(value), currency="GBP")
        return action
    with ThreadPoolExecutor(max_workers=4) as workers:
        operating=[r for r in workers.map(decision,items) if r]
    apollo_body=norm(html.fromstring(fetch(APOLLO_ACTIONS)).xpath("string(//main)"))
    if "No regulatory actions have been recorded" in apollo_body:
        for r in licences:
            if r["account_id"]=="38620":
                r["regulatory_actions_url"]=APOLLO_ACTIONS
    reviewed=json.loads(Path(__file__).with_name("ukgc-reviewed.json").read_text())
    existing={a["case_id"] for a in operating}
    if existing & {r["case_id"] for r in reviewed} or len(existing)!=len(operating):
        raise ValueError("Duplicate proceedings")
    active={r["account_id"] for r in licences if r["eligible"]}
    cutoff=(args.as_of-timedelta(days=365)).isoformat()
    matched=[r for r in operating if cutoff < r["date"] <= checked and r["eligible"] and r["account_id"] in active]
    cited={r["account_id"] for r in matched}
    return dict(id="ukgc",name="Gambling Commission",jurisdiction="Great Britain",role="Gambling licensing and enforcement regulator",
                register_url=REG,enforcement_url=INDEX,observed_at=checked,checked_at=checked,
                coverage=(f"The official exports list {len(accounts):,} business accounts and {len(activity_rows):,} licence-activity rows. "
                          "Rows sharing a licence number, account, status, type and activity dates are grouped. Status applies to the listed activity. "
                          f"The action register contains {len(items)} entries. {len(operating)} operating-account sanctions or settlements are included, "
                          f"plus {len(reviewed)} separately identified historical notices. Personal licence decisions are excluded. "
                          "A retained action register and historical selection are not a complete enforcement history; settlement payments and penalties are distinct."),
                licences=licences,actions=sorted(operating+reviewed,key=lambda x:(x["date"],x["id"]),reverse=True),
                denominator=dict(label="Active operating accounts with a published operating decision in the preceding 365 days",
                                 denominator=len(active),numerator=len(cited),action_count=len({(r["case_id"],r["account_id"]) for r in matched}),action_label="Published operating decisions for accounts in this active cohort",as_of=checked,period_start=(args.as_of-timedelta(days=364)).isoformat(),
                                 period_end=checked,unit="distinct UKGC operating accounts active on the observation date",
                                 basis="The numerator is restricted to the same active account IDs, with a decision dated in the indicated interval on the full public actions register. This is a cross-sectional share among currently active accounts. It does not measure risk across historical licence cohorts.",
                                 url=REG,enforcement_url=INDEX))


if __name__=="__main__":
    args=arguments()
    write_output(collect(args),args.output)
