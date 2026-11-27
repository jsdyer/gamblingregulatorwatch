"""Collect the CGA's linked online licence and enforcement registers. Requires pdfplumber."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen



REGISTER = 'https://www.cga.cw/en/133i348441001'
OUTPUT = Path(__file__).resolve().parents[1] / 'sources' / 'cga.json'
DEFAULT_CERTIFICATES = {
    'OGL/2023/174/0082': 'https://cert.cga.cw/token?id=82',
    'OGL/2023/176/0095': 'https://cert.cga.cw/token?id=95',
}
LICENCE_NO = re.compile(r'(?:CGA|OGL)/\d{4}/\d+/\d+')


class LinkedDocuments(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.label = []
        self.documents = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.label = []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.documents[' '.join(''.join(self.label).lower().split())] = urljoin(REGISTER, self.href)
            self.href = None


class CertificateText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'h1'):
            self.parts = []

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in ('p', 'h1') and self.parts is not None:
            self.blocks.append(' '.join(''.join(self.parts).split()))
            self.parts = None


def download(url):
    request = Request(url, headers={'User-Agent': 'CoolCode public register research (+https://coolcode.ca/)'})
    with urlopen(request, timeout=45) as response:
        if urlsplit(url).hostname == 'cert.cga.cw' and urlsplit(response.geturl()).hostname != 'cert.cga.cw':
            raise ValueError('Certificate redirected away from the official CGA platform')
        return response.read()


def longdate(value):
    value = re.sub(r'\s*,\s*', ', ', value)
    return datetime.strptime(value, '%B %d, %Y').date().isoformat()


def shortdate(value):
    return datetime.strptime(value, '%d-%b-%y').date().isoformat()


def extract_document(content, is_licence):
    import pdfplumber

    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        first = pdf.pages[0].extract_text()
        updated = re.search(r'Last updated\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', first)
        if not updated:
            raise ValueError('Missing CGA register update date')
        for page_number, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for cells in table:
                    cells = [' '.join((cell or '').split()) for cell in cells]
                    if not any(LICENCE_NO.fullmatch(cell) for cell in cells):
                        if any(re.match(r'(CGA|OGL)/', cell) for cell in cells):
                            raise ValueError('Unrecognised CGA licence number')
                        continue
                    if is_licence:
                        number, permit, entity, kind, registration, issued, expires, status = cells
                        if not LICENCE_NO.fullmatch(permit) or kind not in ('B2B', 'B2C'):
                            raise ValueError(f'Unexpected licence columns in {cells}')
                        record = (permit, entity, kind, registration, issued, expires, status)
                        number = int(number)
                    else:
                        index = next(i for i, cell in enumerate(cells) if LICENCE_NO.fullmatch(cell))
                        # One PDF cell can contain both a printed row number and its list marker.
                        markers = {int(cell.strip('.')) for cell in cells[:index] if cell.strip('.').isdigit()}
                        if len(markers) != 1:
                            raise ValueError(f'Unexpected enforcement row number in {cells}')
                        number = markers.pop()
                        permit, entity, registration, effective, status = [cell for cell in cells[index:] if cell]
                        record = (permit, entity, registration, effective, status)
                    if not registration.isdigit() or not entity or number != len(rows) + 1:
                        raise ValueError(f'Incomplete or out-of-sequence CGA row {number}')
                    rows.append((page_number, record))
        if not rows or not re.search(rf'Page\s+{len(pdf.pages)}\s+of\s+{len(pdf.pages)}\b', pdf.pages[-1].extract_text()):
            raise ValueError('Incomplete CGA register')
    return longdate(updated.group(1)), rows


def licences(rows, url, edition):
    result = []
    for page, (permit, entity, kind, registration, issued, expires, published_status) in rows:
        item = dict(entity=entity, licence_id=permit, company_registration=registration,
                    date=shortdate(issued), date_basis='issued', scope=f'Online gaming · {kind}',
                    url=f'{url}#page={page}')
        if re.fullmatch(r'\d{1,2}-[A-Za-z]{3}-\d{2}', expires):
            item['expiry_date'] = shortdate(expires)
        elif expires != 'N/A':
            withdrawal = re.fullmatch(r'Re(?:voked|oked) as of ([A-Za-z]+ \d{1,2},\s*\d{4}),? (?:at the|as) request of the operator\.?', expires, re.I)
            if not withdrawal:
                raise ValueError(f'Unexpected CGA expiry field for {permit}: {expires}')
            item['status_effective_date'] = longdate(withdrawal.group(1))
            item['active'] = False
            published_status = 'Revoked at the request of the operator'
        item['status'] = published_status or 'Status field blank'
        if item['status'].lower().startswith('expired'):
            item['active'] = False
        if item['status'].lower() == 'assessment in progress':
            item['status'] = 'Assessment in progress'
        item['scope'] += f'. Status recorded in the {edition} register.'
        if 'expiry_date' in item:
            item['scope'] += f" Listed expiry date {item['expiry_date']}."
        if 'status_effective_date' in item:
            item['scope'] += f" Effective date {item['status_effective_date']}."
        result.append(item)
    return result


def actions(rows, url):
    result = []
    kinds = {'Revoked': 'Licence revocation', 'Not extended by the CGA': 'Licence non-extension',
             'Suspended': 'Licence suspension'}
    for page, (permit, entity, registration, effective, status) in rows:
        when = longdate(effective)
        kind = kinds[status]
        result.append(dict(id='cga-' + permit.lower().replace('/', '-') + '-' + when, entity=entity,
                           date=when, effective_date=when, type=kind, status=status, eligible=True, foreign_penalty=True,
                           title=f'{kind} · {permit}', licence_id=permit, company_registration=registration,
                           summary=f"The CGA listed this licence as {status.lower()} effective {when}. "
                                   'The register gives the effective date and omits the investigation start.',
                           url=f'{url}#page={page}'))
    return result


def apply_certificate(item, url, content, observed):
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'cert.cga.cw':
        raise ValueError('Expected an official CGA certificate URL')
    page = CertificateText()
    page.feed(content.decode('utf-8'))
    text = ' '.join(page.blocks)
    permit = item['licence_id']
    status = re.search(r'Application status: ([^.?]+)\. License status: ([^.?]+)\.', text)
    holder = re.search(r'This is to certify that (.+?), a company incorporated .*?Company Number (\d+) '
                       r'.*?since (\d{1,2}/[A-Za-z]{3}/\d{4}) .*?under license number (\S+)', text)
    if not holder or not status or 'Certificate B2C' not in page.blocks:
        raise ValueError(f'Unrecognised B2C certificate for {permit}')
    entity, registration, since, listed_permit = holder.groups()
    if (entity, registration, listed_permit) != (item['entity'], item['company_registration'], permit):
        raise ValueError(f'CGA certificate identity differs from register for {permit}')
    since = datetime.strptime(since, '%d/%b/%Y').date().isoformat()
    item['register_record_url'] = item['url']
    item['register_status'] = item['status']
    item['issued_date'] = item['date']
    item['licensed_since'] = since
    item['date'] = observed
    item['date_basis'] = 'observed'
    item['url'] = url
    item['status'] = status[2]
    item.pop('active', None)
    if status[1] == 'Granted' and status[2] == 'Active':
        item['active'] = True
    elif status[2].lower() in {'suspended', 'revoked', 'expired', 'withdrawn', 'inactive'}:
        item['active'] = False
    item['scope'] = (f'B2C online gaming. CGA certificate checked {observed}. Licensed since {since}. '
                     f'The roster lists an issue date of {item["issued_date"]} and status {item["register_status"]}.')


def collect(certificates):
    observed = datetime.now(timezone.utc).date().isoformat()
    links = LinkedDocuments()
    links.feed(download(REGISTER).decode('utf-8'))
    lic_url = links.documents['online gaming licenses']
    act_url = links.documents['enforcement register']
    lic_doc = download(lic_url)
    act_doc = download(act_url)
    lic_edition, lic_rows = extract_document(lic_doc, True)
    act_edition, act_rows = extract_document(act_doc, False)
    licence_records = licences(lic_rows, lic_url, lic_edition)
    action_records = actions(act_rows, act_url)
    requested = {lic['licence_id']: lic for lic in licence_records
                 if lic['status'] == 'Revoked at the request of the operator'}
    for action in action_records:
        voluntary = requested.get(action['licence_id'])
        if voluntary:
            action['foreign_penalty'] = False
            action['summary'] += (f' The licence roster separately records an operator-requested revocation '
                                  f'effective {voluntary["status_effective_date"]}. The sources do not explain '
                                  'the relationship between these entries.')
    for permit, cert_url in certificates.items():
        if urlsplit(cert_url).scheme != 'https' or urlsplit(cert_url).hostname != 'cert.cga.cw':
            raise ValueError('Expected an official CGA certificate URL')
        candidates = [item for item in licence_records if item['licence_id'] == permit]
        if len(candidates) != 1:
            raise ValueError(f'Expected one CGA licence row for certificate {permit}')
        apply_certificate(candidates[0], cert_url, download(cert_url), observed)
    n_permits = len({item['licence_id'] for item in licence_records})
    return dict(
        id='cga', name='Curaçao Gaming Authority', jurisdiction='Curaçao', checked_at=observed,
        role='Licenses and supervises online gaming in Curaçao.',
        register_url=REGISTER, enforcement_url=act_url,
        coverage=(f'All {len(lic_rows)} numbered online gaming licence entries in the {lic_edition} register '
                  f'({n_permits} distinct licence numbers), including B2C operators, B2B suppliers and historical '
                  'statuses. The CGA cautions that a listing does not establish present validity. '
                  f'All {len(act_rows)} entries in the {act_edition} enforcement register are included. '
                  'It records selected decisions affecting licence status and excludes other measures. '
                  'Operator-requested withdrawals in the licence register do not create enforcement cases here. '
                  'Individual CGA certificates are checked for the configured B2C licences. The certificate '
                  'observation date is shown separately from the original licensing and roster issue dates. '
                  'Land-based casinos, lottery permits, and certificates are outside this edition.'),
        licences=licence_records, actions=action_records, licence_certificates=certificates,
        source_versions={'licences': {'as_of': lic_edition, 'url': lic_url, 'sha256': sha256(lic_doc).hexdigest()},
                         'actions': {'as_of': act_edition, 'url': act_url, 'sha256': sha256(act_doc).hexdigest()}})


def refresh(output=OUTPUT):
    certificates = DEFAULT_CERTIFICATES
    if output.exists():
        existing = json.loads(output.read_text(encoding='utf-8'))
        certificates = existing.get('licence_certificates', DEFAULT_CERTIFICATES)
    records = collect(certificates)
    temp_path = None
    try:
        with NamedTemporaryFile('w', dir=output.parent, encoding='utf-8', delete=False) as pending:
            temp_path = Path(pending.name)
            json.dump(records, pending, ensure_ascii=False, indent=2)
            pending.write('\n')
        temp_path.replace(output)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return len(records['licences']), len(records['actions'])


if __name__ == '__main__':
    licence_count, action_count = refresh()
    print(f'Collected {licence_count} CGA licence rows and {action_count} enforcement decisions.')
