"""Check that every submitted result resolves to a complete, source-linked HTML page."""
from pathlib import Path
from lxml import html
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit
import json
root=Path(__file__).resolve().parents[1]/"dist"
site="https://coolcode.ca/gamblingregulatorwatch/"
ed=json.loads((root/"data/edition.json").read_text())
sitemap=[item.text for item in ET.parse(root/"sitemap.xml").findall('.//{*}loc')]
assert len(sitemap)==len(set(sitemap))
n=0
for u in sitemap:
 p=root/u.removeprefix(site)/"index.html"
 d=html.fromstring(p.read_bytes().decode())
 assert d.xpath('count(//h1)') == 1, u
 assert d.xpath('string(//link[@rel="canonical"]/@href)') == u,u
 assert len(d.xpath('string(//title)'))>12,u
 assert len(d.xpath('string(//meta[@name="description"]/@content)'))>15,u
 for href in d.xpath('//a[@href]/@href'):
  s=urlsplit(href)
  if s.netloc or s.scheme or not s.path:continue
  dest=(p.parent/s.path).resolve()
  assert dest.is_relative_to(root),str(dest)
  assert dest.is_file() or (dest/"index.html").is_file(), str(dest)
 n+=1
directory=html.fromstring((root/'records/index.html').read_text())
assert len(directory.xpath('//ul[@class="record-index"]/li/a'))==len(ed["operators"])
assert all((root/'records'/op['slug']/'index.html').is_file() for op in ed['operators'])
print('Verified',n,'sitemap entries and',len(ed['operators']),'directory links; stats',ed['stats'])
