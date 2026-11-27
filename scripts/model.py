"""Build source-traceable operator profiles from reviewed regulatory records."""
from collections import defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def slug(value):
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    label = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:80].rstrip("-")
    return (label or "entity") + "-" + sha256(key(value).encode()).hexdigest()[:10]


def url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"Invalid official source URL {value!r}")
    return value


def iso(value):
    return date.fromisoformat(value[:10]).isoformat()


def reports(source):
    cohort = source.get("denominator") or {}
    if isinstance(cohort.get("action_count"), int) and cohort.get("denominator", 0) > 0:
        n, total = cohort["action_count"], cohort["denominator"]
        return {"value": round(100*n/total, 2), "numerator": n, "denominator": total,
                "year": cohort["period_start"]+" through "+cohort["period_end"],
                "label": "Published business cases per 100 currently active operating accounts",
                "basis": cohort["basis"]+f' The denominator includes active operating accounts across the registered activity classes. {cohort["numerator"]} distinct active accounts had a decision.',
                "url": url(cohort["enforcement_url"])}
    report = source.get("report") or {}
    if not report.get("comparable"):
        return None
    population, actions = report["population"], report["action_count"]
    if not isinstance(population, int) or population <= 0 or not isinstance(actions, int) or actions < 0:
        raise ValueError("Invalid report inputs")
    return {"value": round(100 * actions / population, 2), "numerator": actions,
            "denominator": population, "label": f"{report['action_label']} per 100 {report['population_label']}",
            "year": report["year"], "basis": report["basis"], "url": url(report["url"])}


def resolve_aliases(identities):
    aliases = {}
    for entry in identities:
        names = entry["names"]
        if len(names) < 2 or not entry.get("basis") or len(set(map(url, entry["urls"]))) < 2:
            raise ValueError(f"Identity needs independent receipts: {names}")
        for name in names:
            if key(name) in aliases:
                raise ValueError(f"Overlapping identity mapping: {name}")
            aliases[key(name)] = entry
    return aliases


def cross_border_proofs(entries):
    proofs = {}
    for entry in entries:
        rids = frozenset(entry["regulators"])
        lookup = (key(entry["entity"]),rids)
        if (len(rids)!=2 or len(set(map(url,entry["urls"])))<2 or not entry["basis"] or lookup in proofs):
            raise ValueError("Invalid cross-border identity evidence")
        proofs[lookup] = entry
    return proofs


def edition(sources, identities=(), foreign_matches=()):
    aliases = resolve_aliases(identities)
    proofs = cross_border_proofs(foreign_matches)
    operators, regs, seen = {}, {}, set()
    days = []
    for source in sources:
        rid = source["id"]
        if rid in regs:
            raise ValueError(f"Duplicate regulator {rid}")
        reg = {k: v for k, v in source.items() if k not in {"actions", "licences"}}
        regs[rid] = reg
        for field in ("register_url", "enforcement_url"):
            if reg.get(field):
                url(reg[field])
        checked = source.get("checked_at") or source.get("retrieved") or source.get("as_of")
        if checked:
            days.append(iso(checked))
        reg.update(licence_count=len(source["licences"]), action_count=len(source["actions"]),
                   operator_count=0, case_count=0, repeat_count=0, foreign_count=0, delays=[], rate=reports(source))
        for kind in ("licences", "actions"):
            for raw in source[kind]:
                entity = raw["entity"].strip()
                if not entity:
                    raise ValueError(f"{rid} missing legal name")
                row = dict(raw, regulator=rid)
                url(row["url"])
                if row.get("date"):
                    iso(row["date"])
                identity = aliases.get(key(entity))
                label = identity["names"][0] if identity else entity
                op = operators.setdefault(key(label), dict(slug=slug(label), name=label, licences=[], actions=[],
                                                            foreign=[], delays=[], identity=identity))
                if kind == "actions":
                    action_key = (rid, row["id"], key(entity))
                    if action_key in seen:
                        raise ValueError(f"Duplicate source action {action_key}")
                    seen.add(action_key)
                op[kind].append(row)
    for op in operators.values():
        op["actions"].sort(key=lambda a: (a.get("date") or "", a["id"]), reverse=True)
        op["licences"].sort(key=lambda l: (l["regulator"], l.get("date") or ""), reverse=True)
        by_reg = defaultdict(set)
        for a in op["actions"]:
            if a.get("eligible") is True:
                by_reg[a["regulator"]].add(a.get("case_id") or a["id"])
            if (a.get("effective_date") and a.get("start_date") and a.get("start_basis")
                    and any(kind in a["type"].casefold() for kind in ("revoc", "cancellation")) and a.get("eligible") is True):
                elapsed = (date.fromisoformat(iso(a["effective_date"])) - date.fromisoformat(iso(a["start_date"]))).days
                if elapsed < 0:
                    raise ValueError("Revocation predates start")
                interval = {"days": elapsed, "action": a}
                op["delays"].append(interval)
                regs[a["regulator"]]["delays"].append(interval)
        op["case_count"] = sum(map(len, by_reg.values()))
        op["repeat"] = op["case_count"] >= 2
        for rid in {r["regulator"] for r in op["actions"] + op["licences"]}:
            regs[rid]["operator_count"] += 1
            regs[rid]["repeat_count"] += int(len(by_reg[rid]) >= 2)
            regs[rid]["case_count"] += len(by_reg[rid])
        for lic in op["licences"]:
            if lic.get("active") is not True or lic.get("operator_licence") is False or not lic.get("date") or not lic.get("date_basis"):
                continue
            for a in op["actions"]:
                if a.get("eligible") is True and a.get("foreign_penalty") is True and a["regulator"] != lic["regulator"] and a.get("date") and iso(a["date"]) < iso(lic.get("status_as_of") or lic["date"]):
                    proof = proofs.get((key(op["name"]),frozenset((a["regulator"],lic["regulator"]))))
                    if proof:
                        op["foreign"].append({"action": a, "licence": lic, "identity": proof})

        for rid in {pair["licence"]["regulator"] for pair in op["foreign"]}:
            regs[rid]["foreign_count"] += 1
    result = sorted(operators.values(), key=lambda o: (-bool(o["foreign"]), -o["case_count"], key(o["name"])))
    stats = dict(regulators=len(regs), operators=len(result), actions=sum(r["action_count"] for r in regs.values()),
                 licences=sum(r["licence_count"] for r in regs.values()), repeats=sum(o["repeat"] for o in result),
                 foreign=sum(bool(o["foreign"]) for o in result), intervals=sum(len(o["delays"]) for o in result))
    return dict(built_at=max(days) if days else None, regulators=list(regs.values()), operators=result, stats=stats)


def load_edition():
    directory = ROOT / "sources"
    ids = read(ROOT / "config/regulators.json")
    sources = [read(directory / (i + ".json")) for i in ids]
    if [s["id"] for s in sources] != ids:
        raise ValueError("Source IDs and configured filenames must agree")
    alias_file = directory / "identities.json"
    return edition(sources, read(alias_file) if alias_file.exists() else [],read(ROOT/"config/foreign-matches.json"))
