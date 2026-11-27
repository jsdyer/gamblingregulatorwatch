"""Refresh ACMA's provider export and cross-check Northern Territory licences."""
from argparse import ArgumentParser
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REGISTER = 'https://www.acma.gov.au/check-if-gambling-operator-legal'
EXPORT = 'https://www.acma.gov.au/data/interactive-gambling/json'
NT = 'https://dth.nt.gov.au/boards-and-committees/wagering-commission/licensed-wagering-operators'
FIELDS = {'trading_name', 'license_holder', 'licensing_authority', 'url'}


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'CoolCode Gambling Regulator Watch/1.0'}), timeout=45) as response:
        return response.read()


def clean(text):
    return ' '.join(unescape(text).split())


class NorthernTerritoryTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.current = None
        self.cell = None
        self.rows = []
        self.caption = []
        self.in_caption = False

    def handle_starttag(self, tag, attrs):
        if tag == 'table' and 'licensed in the Northern Territory' in dict(attrs).get('summary',''):
            self.in_table = True
        if not self.in_table:
            return
        if tag == 'caption':
            self.in_caption = True
        if tag == 'tr':
            self.current = []
        elif tag in ('td','th'):
            self.cell = []

    def handle_data(self, data):
        if self.in_caption:
            self.caption.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag == 'caption':
            self.in_caption = False
        if tag in ('td','th') and self.cell is not None:
            self.current.append(clean(''.join(self.cell)))
            self.cell = None
        elif tag == 'tr' and self.current:
            self.rows.append(self.current)
            self.current = None
        elif tag == 'table':
            self.in_table = False


def site(value):
    return (urlsplit(value.strip()).hostname or '').lower().removeprefix('www.')


def licences(register, territory, checked):
    if not isinstance(register, list) or not register:
        raise ValueError('Empty ACMA export')
    table = NorthernTerritoryTable()
    table.feed(territory)
    if not table.rows or table.rows[0] != ['No','Company','Trading as','Website','Comments']:
        raise ValueError('NT licensing table missing or changed')
    stamp = re.search(r'List last updated:\s*(\d{1,2} [A-Za-z]{3,9} \d{4})', clean(''.join(table.caption)), re.I)
    if not stamp:
        raise ValueError('Missing NT register update date')
    date_text = stamp.group(1)
    try:
        nt_as_of = datetime.strptime(date_text, '%d %b %Y').date().isoformat()
    except ValueError:
        nt_as_of = datetime.strptime(date_text, '%d %B %Y').date().isoformat()
    nt = []
    for row in table.rows[1:]:
        if len(row) != 5 or not row[0].isdigit() or not row[1]:
            raise ValueError('Unexpected NT licensed operator row')
        nt.append(row)
    if not nt:
        raise ValueError('Empty NT licence list')
    found = set()
    output = []
    for source in register:
        if not isinstance(source,dict) or not FIELDS <= source.keys():
            raise ValueError('Unknown ACMA export structure')
        if not all(isinstance(source[k], str) for k in FIELDS):
            raise ValueError('Non-text ACMA register field')
        entity, name, authority = [clean(source[k]) for k in ('license_holder','trading_name','licensing_authority')]
        if not all((entity, name, authority)):
            raise ValueError('Missing holder, trading name or licensing authority')
        key = (entity,name,authority)
        if key in found:
            raise ValueError('Duplicate trading name, holder and authority')
        found.add(key)
        status = 'Listed in the ACMA provider export'
        if 'not currently operational' in name.casefold():
            status = 'Listed as not currently operational'
        record = dict(entity=entity, name=name, date=checked, date_basis='observed', status=status,
                      url=EXPORT, scope='Licensing authority in the ACMA export: ' + authority + '.')
        if authority in ('Northern Territory Wagering Commission','NT Director-General of Licensing'):
            domain = site(source['url'])
            match = next((r for r in nt if r[1].casefold()==entity.casefold() and
                          (r[2].casefold()==name.casefold() or (domain and site(r[3])==domain))), None)
            if match is not None:
                comment = match[4]
                if 'not currently' in comment.casefold() or 'suspend' in comment.casefold():
                    record.update(status='NT register: ' + comment, status_as_of=nt_as_of, url=NT, register_url=EXPORT)
                elif match[3] and (not comment or comment == 'Licensed by the Director of Totalisator Licensing and Regulation'):
                    record.update(active=True, operator_licence=True, status_as_of=nt_as_of, status='Listed as licensed by the Northern Territory',
                                  url=NT, register_url=EXPORT)
                    record['scope'] += ' The territory register independently names this holder and trading service.'
        output.append(record)
    return sorted(output, key=lambda r: (r['entity'].casefold(), r['name'].casefold(),r['scope']))


def refresh(output, raw, nt_html, stamp):
    existing = json.loads(output.read_text())
    rows = licences(json.loads(raw),nt_html.decode('utf-8'),stamp)
    if not isinstance(existing.get('actions'), list):
        raise ValueError('Expected reviewed action records')
    existing.update(checked_at=stamp, licences=rows)
    text = json.dumps(existing,ensure_ascii=False,indent=2)+'\n'
    with NamedTemporaryFile(mode='w',encoding='utf-8',dir=output.parent,delete=False) as target:
        target.write(text)
    Path(target.name).replace(output)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--register-file',type=Path,help='Verify a saved copy of the official ACMA JSON export')
    parser.add_argument('--nt-file',type=Path,help='Verify a saved copy of the official NT licensing page')
    parser.add_argument('--as-of',type=date.fromisoformat,help='UTC observation date of supplied copies')
    parser.add_argument('--output',type=Path,default=ROOT/'sources/acma.json')
    args=parser.parse_args()
    if (args.register_file or args.nt_file) and not args.as_of:
        parser.error('Supply --as-of for captured inputs')
    raw=args.register_file.read_bytes() if args.register_file else fetch(EXPORT)
    nt=args.nt_file.read_bytes() if args.nt_file else fetch(NT)
    stamp=args.as_of or datetime.now(timezone.utc).date()
    refresh(args.output, raw, nt, stamp.isoformat())
