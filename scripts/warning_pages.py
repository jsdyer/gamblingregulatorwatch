"""Render the published URL lists for reading and exact-host lookup."""
from html import escape


def render_warnings(stage, sources, shell, link, put):
    path = "records/warnings/"
    labels = {"mga":"Malta Gaming Authority", "tobique":"Tobique Gaming Commission"}
    explanations = {
        "mga":"The authority disclaims an affiliation with each listed URL. Dates are the regulator’s notice dates.",
        "tobique":"The commission separates sites it currently lists from previously listed sites. Dates are the commission’s discovery dates."
    }
    pages = [path]
    nav = []
    for rid, source in sources.items():
        url = path+rid+"/"
        pages.append(url)
        text = explanations[rid]
        name = labels[rid]
        nav.append(link("./"+rid+"/",name+" · "+str(len(source["items"]))+" entries"))
        rows = []
        for item in source["items"]:
            rows.append("<tr><td>"+escape(item["published_as"])+"</td><td>"+escape(item["date"])+"</td><td>"
                        +escape(item["status"])+"</td><td>"+link(item["evidence"],"Regulator record")+"</td></tr>")
        body = ('<h1>'+name+' domain warnings</h1><p>'+text+' Checked '+escape(source["checked_at"])+'. '
                +link(source["source"],"Original warning list")+'</p><p>'+link("../","Search both warning lists")
                +'</p><div style="overflow-x:auto"><table><thead><tr><th>Published URL</th><th>Date</th><th>Listing</th><th>Source</th></tr></thead><tbody>'
                +''.join(rows)+'</tbody></table></div>')
        put(stage/url/"index.html",shell(url,name+" domain warnings",text,body))
    desc = "Look up a gambling website in the published Tobique and Malta domain warning lists, with notice dates and links to the regulators."
    form = ('<form id="warning-search" hidden><label for="warning-host">Website domain or URL</label> '
            '<input id="warning-host" required placeholder="example.ca" spellcheck="false" autocapitalize="none"> '
            '<button type="submit">Find warnings</button></form><div id="matches" role="status"></div>')
    body = ('<h1>Does a regulator list this gambling website?</h1><p>'+desc+'</p>'+form+'<h2>Browse the published lists</h2><ul>'
            +''.join('<li>'+n+'</li>' for n in nav)+'</ul><p>A missing match does not establish a licence. '
            +'Check the '+link("../../regulators/","licensing registers")+' for a positive match.</p>'
            +'<script src="../../warnings.js" defer></script>')
    put(stage/path/"index.html",shell(path,"Gambling website licence warnings by domain",desc,body))
    return pages
