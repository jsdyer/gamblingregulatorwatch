"use strict";
const form = document.querySelector("#warning-search");
const output = document.querySelector("#matches");
const names = {mga: "Malta Gaming Authority", tobique: "Tobique Gaming Commission"};
function hostOf(value) {
  const url = new URL(value.includes("://") ? value : "https://" + value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || !url.hostname.includes(".")) {
    throw new Error("Expected a website domain");
  }
  return url.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
}
async function enable() {
  const response = await fetch("../../data/warnings.json");
  if (!response.ok) throw new Error("Unavailable");
  const sources = await response.json();
  form.hidden = false;
  form.addEventListener("submit", event => {
    event.preventDefault();
    output.replaceChildren();
    let host;
    try { host = hostOf(document.querySelector("#warning-host").value.trim()); }
    catch { output.textContent = "Enter a domain such as example.ca or paste a full website URL."; return; }
    for (const [id, source] of Object.entries(sources)) {
      for (const row of source.items.filter(item => item.host === host)) {
        const p = document.createElement("p");
        const a = document.createElement("a");
        a.href = row.evidence;
        a.textContent = "Read the regulator’s record";
        p.append(names[id] + " · " + row.published_as + " · " + row.status + " · " + row.date + ". ", a);
        output.append(p);
      }
    }
    if (!output.children.length) output.textContent = "No exact published host match for " + host + " in these two lists. Check the licensing registers below.";
  });
}
enable().catch(() => { output.textContent = "Browse either regulator’s saved list below."; });
