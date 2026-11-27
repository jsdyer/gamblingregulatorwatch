from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from model import edition

URL = "https://example.org/records"
NAME = "Example Operator Limited"


def source(rid):
    return dict(id=rid, name=rid, jurisdiction=rid, checked_at="2026-01-31",register_url=URL,
                enforcement_url=URL, coverage="Fixture",actions=[],licences=[])


def action(aid, **fields):
    row = dict(entity=NAME, date="2026-01-01", title="Published order", status="Issued",type="Penalty",url=URL,
               id=aid, eligible=True,foreign_penalty=True)
    return row | fields


def licence(**fields):
    return dict(entity=NAME,date="2026-01-31",date_basis="observed",status="Current",active=True,url=URL) | fields


class Evidence(unittest.TestCase):
    def test_stages_and_eligibility(self):
        r,s=source("home"),source("foreign")
        r["actions"]=[action("a",case_id="one"),action("b",case_id="one",foreign_penalty=False),action("c",eligible=False)]
        s["licences"]=[licence(),licence(entity="Example Operator Holdings Limited"),licence(active=False),licence(date="2025-12-01"),licence(status_as_of="2025-12-01"),licence(operator_licence=False)]
        self.assertEqual(0,edition([r,s])["stats"]["foreign"])
        cross = [dict(entity=NAME,regulators=["home","foreign"],urls=[URL,URL+"/register"],basis="Matching corporate identifiers")]
        data=edition([r,s], foreign_matches=cross)
        p=data["operators"][0]
        self.assertEqual((p["case_count"],p["repeat"],len(p["foreign"])),(1,False,1))
        self.assertEqual(2,len(data["operators"]))
        self.assertIsNone(data["regulators"][0]["rate"])

    def test_confirmed_alias_and_documented_interval(self):
        r=source("a")
        r["licences"]=[licence(entity="Example Operator Ltd.")]
        r["actions"]=[action("x",type="Licence revocation", start_basis="Formal suspension",start_date="2025-12-01",
                             effective_date="2026-01-01"), action("y", type="Licence revocation")]
        aliases=[dict(names=[NAME,"Example Operator Ltd."],urls=[URL,URL+"/other"],basis="Shared registration and legal address")]
        p=edition([r],aliases)["operators"][0]
        self.assertTrue(p["repeat"])
        self.assertEqual(31,p["delays"][0]["days"])
        self.assertEqual(1,len(p["delays"]))
        self.assertEqual([],p["foreign"])
        with self.assertRaises(ValueError):
            edition([r],aliases*2)

    def test_additional_authority_and_duplicate_receipt(self):
        r=source("new"); r["actions"]=[action("one")]
        self.assertEqual(2,edition([source("existing"),r])["stats"]["regulators"])
        r["actions"]+=deepcopy(r["actions"])
        with self.assertRaises(ValueError):
            edition([r])
