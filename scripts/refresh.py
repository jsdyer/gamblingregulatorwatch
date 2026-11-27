#!/usr/bin/env python3
"""Refresh sources independently. Retain the previous complete capture on failure."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from model import ROOT, edition, read


def collect(regulator):
    filename = regulator + ".json"
    with TemporaryDirectory() as directory:
        work = Path(directory)
        shutil.copytree(ROOT/"collectors", work/"collectors",ignore=shutil.ignore_patterns("__pycache__"))
        (work/"sources").mkdir()
        cached = ROOT/"sources"/filename
        captured = work/"sources"/filename
        shutil.copy2(cached, captured)
        if regulator in {"agco", "tobique", "kahnawake"}:
            args = ["canadian_registers.py", regulator]
        else:
            args = [regulator+".py"]
            if regulator in {"ukgc", "ksa"}:
                args.extend(["--output", str(captured)])
        try:
            subprocess.run([sys.executable, str(work/"collectors"/args[0]), *args[1:]],
                           cwd=work, check=True, timeout=720)
            source = read(captured)
            if source["id"] != regulator or not source["licences"] or not source.get("checked_at"):
                raise ValueError("Collector output needs a dated register")
            edition([source])
            pending = cached.with_suffix(".tmp")
            shutil.copyfile(captured, pending)
            pending.replace(cached)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            print(f"Retained {regulator} after collection error: {error}", file=sys.stderr)
            return regulator, False
    return regulator, True


def main():
    regulators = read(ROOT/"config/regulators.json")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(collect, regulators))
    if not any(results.values()):
        raise SystemExit("All source checks failed. The published edition is retained.")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = ROOT/"sources/check.json"
    previous = read(path) if path.exists() else {}
    receipt = {"last_attempt": timestamp, "failed_sources":[k for k,ok in results.items() if not ok],
               "source_checks": dict(previous.get("source_checks",{}))}
    if previous.get("checked_at"):
        receipt["checked_at"] = previous["checked_at"]
    if all(results.values()):
        receipt["checked_at"] = timestamp
    receipt["source_checks"].update({k:timestamp for k,ok in results.items() if ok})
    inbox = ROOT/"sources/notice-index.json"
    try:
        check = subprocess.run([sys.executable,str(ROOT/"collectors/notice_index.py")],cwd=ROOT,timeout=420)
        if check.returncode not in (0,1) or not inbox.exists():
            raise ValueError("Unable to validate publication indexes")
        failures = [s["regulator"] for s in read(inbox)["sources"] if s["availability"]=="unavailable"]
        receipt["failed_notice_indexes"] = failures or (["notice collection"] if check.returncode else [])
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(f"Retaining publication inbox after error: {error}",file=sys.stderr)
        receipt["failed_notice_indexes"]=["notice collection"]
    warnings = subprocess.run([sys.executable,str(ROOT/"collectors/warnings.py")],cwd=ROOT,timeout=180)
    receipt["failed_warning_lists"] = ["domain warnings"] if warnings.returncode else []
    if warnings.returncode and previous.get("checked_at"):
        receipt["checked_at"] = previous["checked_at"]
    elif warnings.returncode:
        receipt.pop("checked_at", None)
    path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(f"Validated {sum(results.values())} of {len(results)} register imports.")


if __name__=="__main__":
    main()
