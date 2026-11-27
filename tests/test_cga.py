import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from collectors import cga


class CGACertificateTests(unittest.TestCase):
    def row(self):
        return {'entity': 'Example N.V.', 'company_registration': '12345',
                'licence_id': 'OGL/2024/1/2', 'date': '2025-12-24', 'url': 'https://regulator.example/licences.pdf#page=2',
                'status': 'Indefinite'}

    def certificate(self, status='Active', entity='Example N.V.'):
        return f"""<h1>Certificate B2C</h1><p>Application status: Granted. License status: {status}.</p>
            <p>This is to certify that {entity}, a company incorporated under the laws of Curaçao with
            Company Number <b>12345 </b>is licensed by the Curaçao Gaming Control Board since 20/Jul/2024 to
            offer games of chance under license number OGL/2024/1/2 in accordance with the LOK.</p>""".encode()

    def test_independent_certificate_observation_has_its_own_date(self):
        row = self.row()
        cga.apply_certificate(row, 'https://cert.cga.cw/token?id=2', self.certificate(), '2026-11-27')
        self.assertTrue(row['active'])
        self.assertEqual((row['date'], row['date_basis']), ('2026-11-27', 'observed'))
        self.assertEqual((row['licensed_since'], row['issued_date']), ('2024-07-20', '2025-12-24'))
        self.assertEqual(row['register_status'], 'Indefinite')

    def test_suspended_certificate_overrides_earlier_roster_status(self):
        row = self.row()
        cga.apply_certificate(row, 'https://cert.cga.cw/token?id=2', self.certificate('Suspended'), '2026-11-27')
        self.assertFalse(row['active'])
        self.assertEqual(row['status'], 'Suspended')

    def test_unclassified_certificate_status_does_not_imply_inactivity(self):
        row = self.row()
        cga.apply_certificate(row, 'https://cert.cga.cw/token?id=2', self.certificate('Pending review'), '2026-11-27')
        self.assertNotIn('active', row)

    def test_certificate_identity_and_source_must_match(self):
        with self.assertRaises(ValueError):
            cga.apply_certificate(self.row(), 'https://cert.cga.cw/token?id=2', self.certificate(entity='Similar N.V.'), '2026-11-27')
        with self.assertRaises(ValueError):
            cga.apply_certificate(self.row(), 'https://cert.cga.cw/token?id=2', b'<html>Service unavailable</html>', '2026-11-27')
        with self.assertRaises(ValueError):
            cga.apply_certificate(self.row(), 'https://example.org/token?id=2', self.certificate(), '2026-11-27')

    def test_source_failure_leaves_previous_file_byte_identical(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'cga.json'
            previous = json.dumps({'licences': [{'entity': 'Earlier record'}], 'actions': []}).encode()
            out.write_bytes(previous)
            with patch.object(cga, 'download', side_effect=TimeoutError('source timeout')):
                with self.assertRaises(TimeoutError):
                    cga.refresh(out)
            self.assertEqual(out.read_bytes(), previous)
            self.assertEqual(list(Path(directory).iterdir()), [out])

    def test_parse_or_write_failure_leaves_previous_file_byte_identical(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'cga.json'
            previous = b'{"licences":[],"actions":[]}'
            out.write_bytes(previous)
            with patch.object(cga, 'collect', side_effect=ValueError('unrecognised register layout')):
                with self.assertRaises(ValueError):
                    cga.refresh(out)
            with patch.object(cga, 'collect', return_value={'licences': [object()], 'actions': []}):
                with self.assertRaises(TypeError):
                    cga.refresh(out)
            self.assertEqual(out.read_bytes(), previous)
            self.assertEqual(list(Path(directory).iterdir()), [out])


if __name__ == '__main__':
    unittest.main()
