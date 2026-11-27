"""Refresh the selected official MGA licence seals. Enforcement notices are reviewed separately."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


OUTPUT = Path(__file__).resolve().parents[1] / 'sources' / 'mga.json'


class SealTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.entity = None
        self.licences = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.stack.append([])
        elif tag in ('th', 'td') and self.stack:
            self.stack[-1].append((dict(attrs).get('class', '').split(), []))

    def handle_data(self, data):
        if self.stack and self.stack[-1]:
            self.stack[-1][-1][1].append(data)

    def handle_endtag(self, tag):
        if tag != 'tr' or not self.stack:
            return
        row = [(classes, ' '.join(''.join(parts).split())) for classes, parts in self.stack.pop()]
        if len(row) == 2 and row[0][1].rstrip(':') == 'Licensee Information':
            self.entity = row[1][1]
        fields = {key: value for classes, value in row for key in classes if key.startswith('cell-license-')}
        if 'cell-license-status' in fields:
            self.licences.append((fields['cell-license-number'], fields['cell-license-type'], fields['cell-license-status']))


def collect_seal(url, observed):
    target = urlsplit(url)
    if (target.scheme, target.netloc, target.path) != ('https', 'authorisation.mga.org.mt', '/verification.aspx'):
        raise ValueError(f'Expected an official MGA seal: {url}')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; CoolCode public register research; +https://coolcode.ca/)'})
    with urlopen(request, timeout=45) as response:
        parser = SealTables()
        parser.feed(response.read().decode('utf-8'))
        parser.close()
    if not parser.entity or not parser.licences:
        raise ValueError(f'Missing licence-level evidence at {url}')
    result = []
    for number, kind, status in parser.licences:
        if not number or not kind or not status:
            raise ValueError(f'Incomplete licence row at {url}')
        result.append(dict(entity=parser.entity, licence_id=number, scope=kind,
                           status=status, active=status.lower() == 'licensed', date=observed,
                           date_basis='observed', url=url))
    return result


def refresh():
    source = json.loads(OUTPUT.read_text())
    urls = source['seal_urls']
    if not urls or len(set(urls)) != len(urls):
        raise ValueError('Expected a nonempty list of unique official MGA seals')
    observed = datetime.now(timezone.utc).date().isoformat()
    checked_today = {}
    for row in source['licences']:
        checked = row.get('status_observed_at') or (row['date'] if row['date_basis'] == 'observed' else None)
        if checked == observed:
            checked_today.setdefault(row.get('status_url') or row['url'], []).append(row)
    rows = []
    for url in urls:
        if url in checked_today:
            rows.extend(checked_today[url])
            continue
        try:
            rows.extend(collect_seal(url, observed))
        except HTTPError as error:
            if error.code != 429:
                raise
            retry = error.headers.get('Retry-After', '60')
            if not retry.isdecimal() or int(retry) > 300:
                raise
            sleep(max(5, int(retry)))
            rows.extend(collect_seal(url, observed))
        sleep(1)

    if len({(row['entity'], row['licence_id']) for row in rows}) != len(rows):
        raise ValueError('Duplicate entity and licence number across MGA seals')
    for row in rows:
        if row['scope'].startswith('B2B'):
            row['operator_licence'] = False
        elif row['scope'].startswith('B2C'):
            row['operator_licence'] = True
        else:
            raise ValueError(f"Unknown MGA licence scope: {row['scope']}")
        decision = source.get('issued_decisions', {}).get(row['licence_id'])
        if decision:
            row.update(date=decision['date'], date_basis='issued', status_url=row.get('status_url') or row['url'],
                       status_observed_at=observed, url=decision['url'])
    source['checked_at'] = observed
    source['licences_checked_at'] = observed
    source['licences'] = sorted(rows, key=lambda item: (item['entity'].casefold(), item['licence_id']))
    with NamedTemporaryFile('w', dir=OUTPUT.parent, encoding='utf-8', delete=False) as temp:
        json.dump(source, temp, ensure_ascii=False, indent=2)
        temp.write('\n')
    Path(temp.name).replace(OUTPUT)
    return len(rows)


if __name__ == '__main__':
    print(f'Refreshed {refresh()} individual MGA licence statuses.')
