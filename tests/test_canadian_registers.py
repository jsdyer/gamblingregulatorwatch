import unittest

from collectors.canadian_registers import read_register


def table(headers, rows):
    return '<table><tr>' + ''.join(f'<th>{v}</th>' for v in headers) + '</tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows) + '</table>'


class CanadianRegisters(unittest.TestCase):
    def test_dual_tobique_classes_and_lapsed_expiry_survive(self):
        sample = table(('Company Name', 'License Expiration Date', 'License Type'),
                       [('Operator Ltd', '2026-11-26', 'B2C'), ('Operator Ltd', '2026-11-28', 'B2B')])
        records, edition = read_register('tobique', sample, '2026-11-27')
        self.assertIsNone(edition)
        self.assertEqual([r['active'] for r in records], [False, True])
        self.assertEqual([r['expiry_date'] for r in records], ['2026-11-26', '2026-11-28'])
        self.assertTrue(all(r['date_basis'] == 'observed' for r in records))

    def test_kahnawake_sites_are_grouped_and_source_does_not_issue_current_status(self):
        sample = ('Updated September 28, 2023. Mohawk Internet Technologies has held the sole IGL.' +
                  table(('OPERATOR', 'URL'), [('One SRL', 'a.example'), ('One SRL', 'b.example')]) +
                  table(('CASINO SOFTWARE PROVIDER AUTHORIZATION HOLDER',), [('Provider Ltd',)]))
        records, edition = read_register('kahnawake', sample, '2026-11-27')
        self.assertEqual(edition, '2023-09-28')
        self.assertEqual(len(records), 3)
        self.assertTrue(all('active' not in row for row in records))

    def test_ontario_status_uses_publication_date_and_can_read_html(self):
        sample = ('Number of Operators: 1 Number of Gaming Websites: 2. The listing is accurate as of '
                  'November 6, 2026. <h3>Sample Ltd</h3><a>Play One</a><a>Play Two</a>')
        rows, edition = read_register('agco', sample, '2026-11-27')
        self.assertEqual(edition, '2026-11-06')
        self.assertEqual(rows[0]['status_as_of'], edition)
        self.assertEqual(rows[0]['date'], '2026-11-27')
        self.assertTrue(rows[0]['active'])
        with self.assertRaisesRegex(ValueError, 'totals'):
            read_register('agco', sample.replace('<a>Play Two</a>', ''), '2026-11-27')
