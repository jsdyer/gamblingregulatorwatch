"""Refresh one reviewed file's public licence register, leaving its decisions untouched.

From the repository root run e.g. python collectors/canadian_registers.py tobique.
Add --input /path/to/register.html --observed YYYY-MM-DD to replay a saved edition.
For Ontario, both the operator and site totals must match the directory header.
Uses the standard library. Dates are UTC. A failed download or parse never replaces data.
"""
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
KGC = 'https://gamingcommission.ca/interactive-gaming/permit-holders/'
TOBIQUE = 'https://thetgc.ca/license-holders/'
ONTARIO = ('https://www.igamingontario.ca/en/operator/operators?'
           'field_legal_entity_name_target_id=All&field_offerings_value=All&items_per_page=100')
URLS = {'kahnawake': KGC, 'tobique': TOBIQUE, 'agco': ONTARIO}


class RegisterHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.open_tables = 0
        self.row = self.cell = None
        self.capture = None
        self.fields = {'h3': [], 'a': []}
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables.append([])
            self.open_tables += 1
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        if tag in self.fields:
            self.capture = (tag, [])

    def handle_data(self, data):
        self.parts.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.capture:
            self.capture[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'table':
            self.open_tables -= 1
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None
        if self.capture and tag == self.capture[0]:
            self.fields[tag].append(' '.join(''.join(self.capture[1]).split()))
            self.capture = None


def dated_label(page, pattern):
    match = re.search(pattern, page, re.I)
    if not match:
        raise ValueError('Public source edition date missing')
    return datetime.strptime(match[1], '%B %d, %Y').date().isoformat()


def read_register(authority, content, observed):
    parser = RegisterHTML()
    parser.feed(content)
    parser.close()
    if parser.open_tables or parser.row is not None:
        raise ValueError('Incomplete register table')
    page = ' '.join(' '.join(parser.parts).split())
    tables = {tuple(row[0]): row[1:] for row in parser.tables if row}
    def record(entity, status, scope, **extra):
        if not entity:
            raise ValueError('Missing entity in directory')
        return dict(entity=entity, date=observed, date_basis='observed', scope=scope, status=status,
                    url=URLS[authority], **extra)
    edition = None
    if authority == 'tobique':
        rows = tables[('Company Name', 'License Expiration Date', 'License Type')]
        result = []
        for entity, expiry, category in rows:
            exp = date.fromisoformat(expiry)
            if category not in {'B2C', 'B2B'}:
                raise ValueError(f'Unexpected licence class: {category}')
            current = exp.isoformat() >= observed
            status = 'Listed; expiry falls on or after observation' if current else 'Listed; published expiry has passed'
            result.append(record(entity, status, f'{category} remote gambling. Register observed {observed}. Published expiry {expiry}.',
                                 active=current, expiry_date=expiry))
    elif authority == 'kahnawake':
        edition = dated_label(page, r'Updated\s+([A-Z]+ \d{1,2}, \d{4})')
        result = []
        for header, scope in [(('OPERATOR', 'URL'), 'Interactive operator'),
                              (('CASINO SOFTWARE PROVIDER AUTHORIZATION HOLDER',), 'Casino software provider')]:
            rows = tables[header]
            if not rows or any(len(row) != len(header) or not row[0] for row in rows):
                raise ValueError(f'Invalid KGC table {header}')
            for entity in sorted({row[0] for row in rows}):
                result.append(record(entity, 'Listed in permit directory', scope + f'. Page update label {edition}.'))
        if 'Mohawk Internet Technologies has held the sole IGL' not in page:
            raise ValueError('Verify the hosting licence statement before refreshing')
        result.append(record('Mohawk Internet Technologies', 'Listed as sole interactive gaming licensee',
                             f'Hosting facility. Sole IGL held since 1999, according to the source observed {observed}.'))
    else:
        edition = dated_label(page, r'listing is accurate as of\s+([A-Z]+ \d{1,2}, \d{4})')
        counts = re.search(r'Number of Operators:\s*(\d+)\s+Number of Gaming Websites:\s*(\d+)', page, re.I)
        names = parser.fields['h3']
        sites = [label for label in parser.fields['a'] if label.startswith('Play ')]
        if not counts or tuple(map(int, counts.groups())) != (len(set(names)), len(sites)):
            raise ValueError('Ontario operator or website totals do not reconcile; check pagination')
        result = []
        for name in names:
            entity, brand = name, None
            if ' (dba) ' in name:
                entity, brand = name.split(' (dba) ', 1)
            elif re.search(r' \([^()]+\)$', name) and name.endswith(')'):
                entity, brand = name.rsplit(' (', 1)
                brand = brand[:-1]
            result.append(record(entity, 'Listed in Ontario’s regulated market',
                                 f'iGaming Ontario-contracted operator. Directory current to {edition}.',
                                 active=True, status_as_of=edition, **({'name': brand} if brand else {})))
    if not result or len(result) != len({(r['entity'], r['scope']) for r in result}):
        raise ValueError('Empty or duplicate register records')
    return result, edition


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('authority', choices=sorted(URLS))
    cli.add_argument('--input', type=Path)
    cli.add_argument('--observed', type=date.fromisoformat)
    args = cli.parse_args()
    if args.input and not args.observed:
        cli.error('Saved files require their original --observed date')
    observed = (args.observed or datetime.now(timezone.utc).date()).isoformat()
    if args.input:
        data = args.input.read_bytes()
    else:
        request = Request(URLS[args.authority], headers={'User-Agent': 'CoolCode public register research'})
        with urlopen(request, timeout=45) as response:
            data = response.read()
    records, edition = read_register(args.authority, data.decode('utf-8-sig'), observed)
    path = ROOT / 'sources' / (args.authority + '.json')
    bundle = json.loads(path.read_text(encoding='utf-8'))
    bundle.update(licences=records, checked_at=observed)
    version = dict(observed=observed, url=URLS[args.authority], sha256=sha256(data).hexdigest())
    if edition:
        version['as_of'] = edition
    bundle.setdefault('source_versions', {})['licences'] = version
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as tmp:
        json.dump(bundle, tmp, ensure_ascii=False, indent=2)
        tmp.write('\n')
    replacement = Path(tmp.name)
    replacement.chmod(path.stat().st_mode & 0o777)
    replacement.replace(path)
    print(f'{args.authority}: {len(records)} licence records observed {observed}')


if __name__ == '__main__':
    main()
