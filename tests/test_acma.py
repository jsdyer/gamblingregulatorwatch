import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from collectors.acma import EXPORT, NT, licences, refresh


REGISTER = [{'trading_name':'Example Sports','license_holder':'Example Pty Ltd','url':'https://sports.example',
             'licensing_authority':'Northern Territory Wagering Commission'}]
TERRITORY = '''<table summary="Sports bookmakers and betting exchange operators licensed in the Northern Territory">
<caption>List last updated: 26 Nov 2026.</caption><tr><th>No</th><th>Company</th><th>Trading as</th>
<th>Website</th><th>Comments</th></tr><tr><td>1</td><td>Example Pty Ltd</td><td>Example Sports</td>
<td>https://sports.example</td><td></td></tr></table>'''


class AcmaSource(unittest.TestCase):
    def test_active_depends_on_territory_register_match(self):
        row, = licences(REGISTER, TERRITORY, '2026-11-27')
        self.assertEqual((row['url'], row['date'], row['status_as_of']), (NT, '2026-11-27', '2026-11-26'))
        self.assertTrue(row['active'])
        for html in (TERRITORY.replace('Example Pty Ltd', 'Other Pty Ltd'),
                     TERRITORY.replace('<td></td>', '<td>Not currently trading</td>')):
            result, = licences(REGISTER, html, '2026-11-27')
            self.assertNotIn('active', result)

    def test_changed_or_empty_input_preserves_reviewed_snapshot(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'acma.json'
            original=json.dumps({'checked_at':'2026-01-01', 'actions':[{'id':'signed-case'}]})
            path.write_text(original)
            for raw,html in ((b'[]',TERRITORY), (json.dumps(REGISTER).encode(),'<html>Unavailable</html>'),
                             (json.dumps(REGISTER*2).encode(),TERRITORY)):
                with self.assertRaises(ValueError):refresh(path,raw,html.encode(),'2026-11-27')
                self.assertEqual(path.read_text(),original)
            refresh(path,json.dumps(REGISTER).encode(),TERRITORY.encode(),'2026-11-27')
            self.assertEqual(json.loads(path.read_text())['actions'],[{'id':'signed-case'}])
