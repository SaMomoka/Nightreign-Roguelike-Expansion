import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from relic_selection import RelicSelection, menu_blueprint


def entry(i, kind, required="none", negative=False, order=None):
    return dict(effect_id=i, selectable_modes=[kind], is_negative=negative,
        deep_random=kind=="deep" and not negative, curse_random=negative,
        curse_requirement="negative" if negative else required,
        names={"zhocn": "词条"+str(i)}, allowed_characters=["Ironeye"], order=order or i)


def fixture():
    return dict(entries=[entry(i,"normal") for i in range(1,9)] +
        [entry(10,"deep","required"),entry(11,"deep","required"),
         entry(12,"deep"),entry(13,"deep"),entry(14,"deep"),
         entry(20,"deep",negative=True),entry(21,"deep",negative=True)])


class FullRelicSelectionTests(unittest.TestCase):
    def setUp(self):
        self.model=RelicSelection(fixture())

    def test_required_positive_opens_negative_then_commits_pair(self):
        self.assertEqual(self.model.choose_positive(2,0,10),"choose_negative")
        self.assertIsNone(self.model.drafts[2][0]["effect_id"])
        self.model.choose_negative(21)
        self.assertEqual(self.model.drafts[2][0],dict(effect_id=10,curse_id=21))

    def test_free_positive_clears_previous_curse(self):
        self.model.choose_positive(2,0,10);self.model.choose_negative(20)
        self.assertEqual(self.model.choose_positive(2,0,12),"editor")
        self.assertEqual(self.model.drafts[2][0],dict(effect_id=12,curse_id=None))

    def test_cancel_negative_restores_prior_pair(self):
        self.model.choose_positive(2,0,10);self.model.choose_negative(20)
        self.model.choose_positive(2,0,11);self.model.cancel_negative()
        self.assertEqual(self.model.drafts[2][0],dict(effect_id=10,curse_id=20))

    def test_four_drafts_independent_and_retained(self):
        self.model.choose_positive(0,0,1);self.model.choose_positive(1,0,2)
        self.model.choose_positive(2,0,12);self.model.choose_positive(3,0,13)
        self.assertEqual([d[0]["effect_id"] for d in self.model.drafts],[1,2,12,13])

    def test_incomplete_and_pending_cannot_craft(self):
        with self.assertRaises(ValueError):self.model.request(0)
        for slot,i in enumerate((12,13,14)):self.model.choose_positive(2,slot,i)
        self.model.choose_positive(2,0,10)
        with self.assertRaises(ValueError):self.model.request(2)

    def test_duplicate_and_cross_kind_rejected(self):
        self.model.choose_positive(0,0,1)
        for args in [(0,1,1),(0,1,10),(2,0,20)]:
            with self.assertRaises(ValueError):self.model.choose_positive(*args)

    def test_order_keeps_negative_with_its_positive(self):
        self.model.choose_positive(2,2,10);self.model.choose_negative(21)
        self.model.choose_positive(2,0,14);self.model.choose_positive(2,1,12)
        r=self.model.request(2)
        self.assertEqual(r["bundles"][0],dict(effect_id=10,curse_id=21))
        self.assertEqual((r["price"],r["currency_cost_type"]),(1,4))

    def test_stale_and_duplicate_acknowledgements_rejected(self):
        for slot,i in enumerate((1,2,3)):self.model.choose_positive(0,slot,i)
        r=self.model.request(0)
        ack=dict(r,runtime_verified=True,shop_id=999)
        self.model.choose_positive(0,0,4)
        with self.assertRaises(ValueError):self.model.verify_ack(ack)
        r=self.model.request(0);ack=dict(r,runtime_verified=True,shop_id=999)
        self.assertEqual(self.model.verify_ack(ack),999)
        with self.assertRaises(ValueError):self.model.verify_ack(ack)

    def test_pagination_covers_every_candidate_once(self):
        result=menu_blueprint(fixture())
        pages=result["pickers"][0]["pages"]
        self.assertEqual([x["effect_id"] for p in pages for x in p["choices"]],list(range(1,9)))
        self.assertTrue(all(len(p["choices"])<=6 for p in pages))
        self.assertFalse(result["runtime_bound"])
        self.assertIsNone(result["runtime_adapter"])

    def test_cannot_select_negative_without_positive(self):
        with self.assertRaises(ValueError):self.model.choose_negative(20)

    def test_duplicate_negative_rejected_without_losing_pending(self):
        self.model.choose_positive(2,0,10);self.model.choose_negative(20)
        self.model.choose_positive(2,1,11)
        with self.assertRaises(ValueError):self.model.choose_negative(20)
        self.model.choose_negative(21)
        self.assertEqual(self.model.drafts[2][1]["curse_id"],21)

    def test_native_group_conflict_keeps_previous_draft(self):
        self.model.entries[1]["compatibility_id"]=7
        self.model.entries[2]["compatibility_id"]=7
        self.model.choose_positive(0,0,1)
        with self.assertRaises(ValueError):self.model.choose_positive(0,1,2)
        self.assertIsNone(self.model.drafts[0][1]["effect_id"])
