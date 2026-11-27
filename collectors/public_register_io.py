"""Public regulator downloads. pip install lxml; output is optional and atomic."""
from argparse import ArgumentParser
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlparse


def arguments():
    p = ArgumentParser(description=__doc__)
    p.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    p.add_argument("--cache", type=Path, help="Optional exact-response directory for one observation date; use a new directory for a new run")
    p.add_argument("--output", type=Path, help="Write only after all sources validate; otherwise write JSON to stdout")
    return p.parse_args()


def download(url, cache=None):
    if urlparse(url).scheme != "https":
        raise ValueError("Expected official HTTPS source")
    path = cache / sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():
        return path.read_bytes()
    req = Request(url, headers={"User-Agent": "CoolCode catalogue research (+https://coolcode.ca/)"})
    with urlopen(req, timeout=35) as response:
        data = response.read()
    if not data:
        raise ValueError("Empty source response")
    if path:
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
    return data


def write_output(obj, path):
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if not path:
        print(text, end="")
        return
    path.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as fp:
        try:
            fp.write(text)
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            os.unlink(fp.name)
            raise
    os.replace(fp.name, path)
