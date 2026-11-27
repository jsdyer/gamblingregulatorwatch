"""Readable, source-linked pages for the eight authority files and review inbox."""
from html import escape


def write_directories(stage, ed, checks, render_page, link, put):
    regs = {r["id"]: r for r in ed["regulators"]}
    urls = ["regulators/"]
    cards = []
    for rid, reg in regs.items():
        route = f"regulators/{rid}/"
        urls.append(route)
        enc = lambda value: escape(str(value),quote=True)
        title = reg["name"]+" — licence and enforcement records"
        current = reg.get("checked_at") or ed["built_at"]
        sections = [f'<h1>{enc(reg["name"])}</h1><p>{enc(reg["jurisdiction"])} · Snapshot dated {enc(current)}</p>',
                    f'<p>{enc(reg["role"])}</p><p>{enc(reg["coverage"])}</p>',
                    f'<p>{link(reg["register_url"],"Official register")}',]
        if reg.get("enforcement_url"):
            sections[-1] += " · "+link(reg["enforcement_url"],"Official enforcement source")
        sections[-1] += "</p>"
        if rid in checks.get("failed_sources",[]):
            sections.append('<p>The latest automated register check failed. This page retains the previous successful snapshot.</p>')
        rows = [("Included licence records",reg["licence_count"]),("Published enforcement records",reg["action_count"]),
                ("Distinct qualifying entity–case pairs",reg["case_count"]),("Entities with multiple qualifying cases from this regulator",reg["repeat_count"]),
                ("Entities with later licensing evidence here after a confirmed foreign penalty",reg["foreign_count"])]
        sections.extend(['<h2>What this edition covers</h2><dl>',
                         ''.join(f'<dt>{enc(label)}</dt><dd>{value:,}</dd>' for label,value in rows),'</dl>'])
        rate = reg["rate"]
        if rate:
            sections.append(f'<h2>Enforcement rate within the documented population</h2><p><strong>{rate["value"]:.2f}</strong> {enc(rate["label"])}. The calculation uses {rate["numerator"]} divided by {rate["denominator"]:,}, multiplied by 100. The reporting period is {enc(rate["year"])}.</p><p>{enc(rate["basis"])} {link(rate["url"],"Population and reporting source")}</p>')
        else:
            sections.append('<p>A comparable enforcement rate is unavailable. This edition lacks a verified count of actions and licensed entities for the same population and reporting period.</p>')
        if reg["delays"]:
            sections.append('<h2>Documented revocation intervals</h2><ul>')
            for d in reg["delays"]:
                a=d["action"]
                sections.append(f'<li>{enc(a["entity"])} — {d["days"]} days from {enc(a["start_basis"])} ({enc(a["start_date"])}) to the effective date ({enc(a["effective_date"])}). {link(a["url"],"Decision")}</li>')
            sections.append('</ul>')
        rows=[]
        for op in ed["operators"]:
            for a in op["actions"]:
                if a["regulator"]==rid:
                    rows.append((a["date"],op,a))
        if rows:
            sections.append('<h2>Included decisions and notices</h2><ul>')
            for _,op,a in sorted(rows,key=lambda item:item[0],reverse=True):
                sections.append(f'<li>{enc(a["date"])} · {link("../../records/"+op["slug"]+"/",op["name"])} · {enc(a["title"])} · {link(a["url"],"Official record")}</li>')
            sections.append('</ul>')
        else:
            sections.append('<p>This edition contains no reviewed named-entity action for this authority. Enforcement activity may also be unpublished or reported elsewhere.</p>')
        sections.append(f'<p>{link("../../#regulators","Open the interactive comparison")} · {link("../","Browse all authorities")}</p>')
        put(stage/route/"index.html",render_page(route,title,reg["coverage"],"".join(sections)))
        cards.append(f'<li>{link("./"+rid+"/",reg["name"])} — {enc(reg["jurisdiction"])}. {reg["licence_count"]:,} licence records and {reg["action_count"]:,} published enforcement records.</li>')
    desc = "Compare licence records, enforcement coverage, reporting periods and official sources."
    body = '<h1>Gambling regulators and their public records</h1><p>'+desc+'</p><ul>'+''.join(cards)+'</ul>'
    put(stage/"regulators/index.html",render_page("regulators/","Gambling regulator records by jurisdiction",desc,body))
    return urls


def write_notices(stage,inbox,render_page,link,put):
    nodes = ["<h1>Regulatory notices to review</h1><p>These links were found in official publication indexes. A newly listed notice can be a consultation, correction, or case update. Only reviewed evidence enters an operator’s enforcement counts.</p>"]
    nodes.append("<p>Index checked "+escape(inbox["checked_at"])+". A first observation establishes the baseline. Subsequent changes are marked when an index exposes them.</p>")
    for source in inbox.get("sources",[]):
        rid=source.get("regulator",source.get("id"))
        nodes.append("<h2>"+escape(source.get("name",rid) or "Source")+"</h2>")
        if source.get("index_url"):
            nodes.append("<p>"+link(source["index_url"],"Official publication index")+"</p>")
        nodes.append("<p>"+escape(str(source.get("coverage","")))+" "+escape(str(source.get("status","")))+"</p>")
        notices=[n for n in inbox.get("notices",[]) if n["regulator"]==rid and n.get("listed",True)]
        if notices:
            nodes.append('<ul>')
            for n in notices:
                date=n.get("published_on") or "Publication date unavailable"
                state="Linked to reviewed evidence" if n.get("reviewed") else "Awaiting review"
                if n.get("is_new"):
                    state += " · Newly discovered"
                if n.get("is_updated"):
                    state += " · Publisher updated the notice"
                nodes.append("<li>"+link(n["url"],n["title"])+" · "+escape(date)+" · "+state+"</li>")
            nodes.append('</ul>')
    put(stage/"notices/index.html", render_page("notices/","Official gambling notices to review","Browse recently listed publications in selected official regulator indexes.",''.join(nodes)))
