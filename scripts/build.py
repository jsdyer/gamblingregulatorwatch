#!/usr/bin/env python3
"""Render the explorer and source-linked, crawlable pages from local snapshots."""
from datetime import date
from html import escape
from pathlib import Path
import json
import shutil
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from model import ROOT, load_edition, read, url
from search_metadata import add_search_metadata
from directories import write_directories, write_notices

BASE = "https://coolcode.ca/gamblingregulatorwatch/"
NAME = "Gambling Regulator Watch"


def e(value):
    return escape(str(value), quote=True)


def link(href, label):
    return f'<a href="{e(href)}">{e(label)}</a>'


def official(value, label):
    return link(url(value), label)


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def dump(path, obj):
    put(path, json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def shell(path, title, desc, body):
    root = "../" * path.count("/")
    return f'''<!doctype html>
<html lang="en-CA"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · {NAME}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{BASE}{path}"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<link rel="stylesheet" href="{root}style.css"><link rel="icon" href="{root}favicon.svg">
<script defer src="/assets/tool-metrics.js" referrerpolicy="no-referrer"></script></head>
<body data-tool-id="gamblingregulatorwatch"><a class="skip" href="#main">Skip to evidence</a>
<header class="masthead"><div class="wrap masthead-inner">{link(root, NAME)} {link("https://coolcode.ca/", "CoolCode.ca")}</div></header>
<main class="wrap profile" id="main">{body}</main>
<footer class="wrap">{link(root+"records/", "All operator records")} · {link(root+"#coverage", "Sources and coverage")} · {link("https://coolcode.ca/report/?tool=gamblingregulatorwatch", "Report a correction")}</footer></body></html>'''


def action_text(a):
    return a.get("summary") or a["title"]


def profile(op, regs):
    summary = []
    if op["actions"]:
        latest = op["actions"][0]
        summary.append(f'{regs[latest["regulator"]]["name"]} published the most recent included action on {latest["date"]}.')
    if op["licences"]:
        names = sorted({regs[l["regulator"]]["name"] for l in op["licences"]})
        summary.append(f'Licence evidence appears in {", ".join(names)}.')
    return " ".join(summary)


def profile_page(op, regs):
    summary = profile(op, regs)
    path = "records/" + op["slug"] + "/"
    rows = [f'<h1>{e(op["name"])}</h1><p>{e(summary)}</p><p>{link("../../?operator="+op["slug"]+"#operators","Open this operator in the explorer")}</p>']
    if op["identity"]:
        identity = op["identity"]
        refs = " · ".join(official(href, f"Identity source {i}") for i, href in enumerate(identity["urls"],1))
        rows.append(f'<h2>Legal-name match</h2><p>{e(identity["basis"])} {refs}</p>')
    if op["foreign"]:
        rows.append('<h2>Foreign penalty and later licence evidence</h2><p>Each pair names the same legal entity. A later observation establishes its published status on that date. It cannot establish uninterrupted licensing or what a regulator knew.</p><ul>')
        pairs = set()
        for pair in op["foreign"]:
            a, l = pair["action"], pair["licence"]
            uid = (a["url"], l["url"], l["date"],l.get("licence_id"))
            if uid in pairs:
                continue
            pairs.add(uid)
            proof = pair["identity"]
            refs = " · ".join(official(href, f"Source {i}") for i,href in enumerate(proof["urls"],1))
            certified = l.get("status_as_of") or l["date"]
            rows.append(f'<li>{official(a["url"], regs[a["regulator"]]["name"]+" · "+a["date"])} — {e(a["title"])}. {official(l["url"], regs[l["regulator"]]["name"]+" · "+certified)} — {e(l["status"])} ({e(l["date_basis"])}). <small>{e(proof["basis"])} {refs}</small></li>')
        rows.append('</ul>')
    if op["delays"]:
        rows.append("<h2>Time to effective revocation</h2>")
        for d in op["delays"]:
            a = d["action"]
            before = " "+official(a["start_url"],"Starting notice") if a.get("start_url") else ""
            rows.append(f'<p>{d["days"]} days from {e(a["start_basis"])} ({e(a["start_date"])}) to effective revocation ({e(a["effective_date"])}). {official(a["url"],"Decision")}{before}</p>')
    for a in op["actions"]:
        if a.get("start_date") and a.get("interval_end") and a.get("end_basis"):
            n = (date.fromisoformat(a["interval_end"]) - date.fromisoformat(a["start_date"])).days
            rows.append(f'<h2>Documented case interval</h2><p>{n} days from {e(a["start_basis"])} ({e(a["start_date"])}) to {e(a["end_basis"])} ({e(a["interval_end"])}). {official(a["url"],"Official notice")}</p>')
    if op["actions"]:
        rows.append(f'<h2>Published enforcement records</h2><p>{op["case_count"]} distinct qualifying case outcome(s) within the included sources. Multiple decisions can concern different conduct.</p>')
        for a in op["actions"]:
            rows.append(f'<article><h3>{e(a["title"])}</h3><p>{e(regs[a["regulator"]]["name"])} · {e(a["date"])} · {e(a["status"])}</p><p>{e(action_text(a))}</p><p>{official(a["url"],"Read the official record")}</p></article>')
    if op["licences"]:
        rows.append('<h2>Licence records</h2><ul>')
        for l in op["licences"]:
            detail = " · ".join(str(x) for x in [l.get("name"), l.get("scope"), l.get("licence_id"), l.get("date"), l.get("date_basis"), ("Source effective "+l["status_as_of"]) if l.get("status_as_of") else None] if x)
            rows.append(f'<li><strong>{e(regs[l["regulator"]]["name"])}</strong> — {e(l["entity"])} · {e(l["status"])}. {e(detail)}. {official(l["url"],"Licensing source")}</li>')
        rows.append("</ul>")
    rows.append("<h2>Coverage for this profile</h2>")
    for rid in dict.fromkeys(r["regulator"] for r in op["actions"] + op["licences"]):
        reg = regs[rid]
        rows.append(f'<p><strong>{e(reg["name"])}</strong> — {e(reg["coverage"])} {official(reg["enforcement_url"],"Enforcement source") if reg.get("enforcement_url") else ""}</p>')
    return shell(path, op["name"]+" — licence and enforcement records", summary, "".join(rows))


def render(stage, ed):
    if not ed["operators"] or not ed["built_at"]:
        raise ValueError("A dated, populated edition is required")
    regs = {r["id"]:r for r in ed["regulators"]}
    shutil.copytree(ROOT/"web",stage,dirs_exist_ok=True)
    dump(stage/"data/edition.json",ed)
    status = dict(edition_date=ed["built_at"], **ed["stats"])
    check = ROOT/"sources/check.json"
    if check.exists():
        status.update(read(check))
    dump(stage/"data/status.json",status)
    pages = ["records/"] + write_directories(stage,ed,status,shell,link,put)
    inbox = ROOT/"sources/notice-index.json"
    more = link("./regulators/","Browse regulator profiles")
    if inbox.exists():
        write_notices(stage,read(inbox),shell,link,put)
        more += " · "+link("./notices/","Official notices awaiting review")
    ops = ed["operators"]
    op = next((p for p in ops if p["foreign"]),next(p for p in ops if p["actions"]))
    # Prefer the documented Ontario/Great Britain example while both receipts exist.
    for candidate in ops:
        if candidate["name"].casefold() == "videoslots limited" and candidate["foreign"]:
            op = candidate
            break
    pair = next((p for p in op["foreign"] if p["licence"]["regulator"] == "agco" and p["action"]["regulator"] == "ukgc"),
                op["foreign"][0] if op["foreign"] else None)
    a = pair["action"] if pair else op["actions"][0]
    feature_text = a["title"]+". "+regs[a["regulator"]]["name"]+" published this record on "+a["date"]+"."
    if a.get("amount") and a.get("currency"):
        feature_text = regs[a["regulator"]]["name"]+" recorded a "+a["currency"]+" "+format(a["amount"],",")+" "+a["type"].lower()+"."
    if pair:
        lic = pair["licence"]
        if lic["regulator"] == "agco":
            feature_text += " iGaming Ontario listed the same operator in its "+(lic.get("status_as_of") or lic["date"])+" directory."
        else:
            feature_text += " A later licence record from "+regs[lic["regulator"]]["name"]+" names the same company."
    feature = (f'<span class="feature-label">Featured operator record</span><time datetime="{e(a["date"])}">{e(a["date"])}</time>'
               f'<h2>{e(op["name"])}</h2><p>{e(feature_text)}</p>{link("./records/"+op["slug"]+"/","Read the operator record →")}')
    html = (stage/"index.html").read_text()
    if html.count("{{FEATURE}}") != 1:
        raise ValueError("Missing featured evidence slot")
    tool = read(ROOT/"tool.json")
    more += " · "+link("./data/status.json","Source check status")+" · "+link("./data/edition.json","Download source-linked data")
    schedule = "Register checks are scheduled for Fridays at 09:43 UTC. Each source keeps its own observation date."
    if status.get("failed_sources"):
        retained = ", ".join(regs[k]["name"] for k in status["failed_sources"] if k in regs)
        schedule += " The "+status["last_attempt"][:10]+" check retained the previous snapshot for "+retained+"."
    more = e(schedule)+"</p><p>"+more
    related = '<p><strong>Related investigation.</strong> '+link("https://coolcode.ca/registrarwatch/","Explore phishing reports by domain registrar")+' to see how a different industry measures reports against portfolio size.</p>'
    if 'rel="icon"' not in html:
        html=html.replace("</head>",'<link rel="icon" href="./favicon.svg"></head>')
    html = html.replace("</main>", '<section class="coverage"><div><h2>Sources and updates</h2></div><div class="coverage-copy"><p>'+more+'</p>'+related+'</div></section></main>')
    html = add_search_metadata(html.replace("{{FEATURE}}",feature),tool,category="ReferenceApplication")
    put(stage/"index.html",html)
    for op in ops:
        page = "records/"+op["slug"]+"/"
        put(stage/page/"index.html",profile_page(op,regs))
        # Curate discovery around substantive decisions or cross-register evidence.
        if op["actions"] or len({l["regulator"] for l in op["licences"]})>1:
            pages.append(page)
    ordered = sorted(ops,key=lambda op:op["name"].casefold())
    anchors = [f'<li>{link("./"+op["slug"]+"/",op["name"])}</li>' for op in ordered]
    body = (f'<h1>Gambling operator records</h1><p>Find licence entries and regulatory decisions for {len(ops):,} named entities. Latest included source snapshot {e(ed["built_at"])}.</p>'
            f'<p>{link("../#operators","Search and filter records")} · {link("../#coverage","Read the coverage notes")}</p><ul class="record-index">'+''.join(anchors)+'</ul>')
    put(stage/"records/index.html",shell("records/","Gambling operator records by legal name","Browse published gambling licences and enforcement records by legal entity.",body))
    root = ET.Element("urlset",xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for path in sorted(pages):
        ET.SubElement(ET.SubElement(root,"url"),"loc").text=BASE+path
    put(stage/"sitemap.xml",ET.tostring(root,encoding="unicode",xml_declaration=True))
    put(stage/".nojekyll","")
    if not (stage/"favicon.svg").exists():
        shutil.copyfile(ROOT/"assets/favicon.svg",stage/"favicon.svg")
    print(f'{len(ops)} linked profiles, {len(pages)} sitemap entries')


def main():
    ed = load_edition()
    with TemporaryDirectory(dir=ROOT) as tmp:
        stage = Path(tmp)/"site"
        render(stage,ed)
        destination = ROOT/"dist"
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)


if __name__=="__main__":
    main()
