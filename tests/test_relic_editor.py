import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from relic_editor import drafts, NORMAL, DEEP_FIRST, DEEP_FREE, CURSE, audit_plan


def fixture():
    """Small independent contract fixture; real 83-product plan is tested separately."""
    pages=[];products=[];purchases=[]
    for owner in range(4):
        start=200000+owner*10
        effects=list(NORMAL[:3]) if owner<2 else [DEEP_FIRST[0],*DEEP_FREE[:2]]
        products.append(dict(shop_id=1900200000+owner,relic_id=9000000+owner,effects=effects,
                             curses=[None]*3 if owner<2 else [CURSE,None,None],
                             kind="normal" if owner<2 else "deep"))
        purchases.append(dict(state=start+4,shop_id=1900200000+owner,back=start))
        pages.append(dict(state=start,back=10,editor=owner,selection=list(effects),
                          entries=[dict(text_id=1900300000,target=start)]*3+
                                  [dict(text_id=1900300000,target=start+4),dict(text_id=1900300000,target=10)]))
    return dict(products=products,pages=pages,purchases=purchases,texts=[dict(id=1900300000)],
                original_shop_state=210000,price=1,currency_cost_type=4)


class RelicEditorTests(unittest.TestCase):
    def test_normal_orderings_can_edit_each_slot_without_duplicates(self):
        rows=drafts((NORMAL,)*3)
        self.assertIn((0,0,0),rows)
        self.assertIn((NORMAL[2],NORMAL[0],NORMAL[1]),rows)
        self.assertNotIn((NORMAL[0],NORMAL[0],0),rows)
        self.assertEqual(len({tuple(sorted(v)) for v in rows if all(v)}),20)

    def test_deep_slots_keep_required_and_free_pools_separate(self):
        rows=drafts((DEEP_FIRST,DEEP_FREE,DEEP_FREE))
        self.assertTrue(all(v[0]==0 or v[0] in DEEP_FIRST for v in rows))
        self.assertNotIn((DEEP_FREE[0],DEEP_FIRST[0],DEEP_FREE[1]),rows)
        self.assertEqual(len({tuple(sorted(v)) for v in rows if all(v)}),63)

    def test_four_five_choice_editors_with_native_purchase(self):
        self.assertTrue(audit_plan(fixture()))

    def test_incomplete_draft_cannot_purchase(self):
        plan=fixture();plan["pages"][0]["selection"][0]=0
        with self.assertRaises(ValueError):audit_plan(plan)
        plan["pages"][0]["entries"][3]["target"]=plan["pages"][0]["state"]
        self.assertTrue(audit_plan(plan))

    def test_invalid_price_currency_and_curse_rejected(self):
        for mutation in ("price","currency","curse"):
            plan=fixture()
            if mutation=="price":plan["price"]=2
            if mutation=="currency":plan["currency_cost_type"]=0
            if mutation=="curse":plan["products"][2]["curses"]=[None]*3
            with self.assertRaises(ValueError):audit_plan(plan)

    def test_wrong_product_and_normal_deep_crossing_rejected(self):
        plan=fixture();plan["purchases"][0]["shop_id"]=plan["products"][2]["shop_id"]
        with self.assertRaises(ValueError):audit_plan(plan)

    def test_targets_cannot_bypass_native_modal_wait(self):
        plan=fixture();plan["pages"][0]["entries"]=copy.deepcopy(plan["pages"][0]["entries"])
        plan["pages"][0]["entries"][0]["target"]=200003
        with self.assertRaises(ValueError):audit_plan(plan)

    def test_missing_choice_and_duplicate_allocation_rejected(self):
        plan=fixture();plan["pages"][1]["entries"].pop()
        with self.assertRaises(ValueError):audit_plan(plan)
        plan=fixture();plan["products"][1]["relic_id"]=plan["products"][0]["relic_id"]
        with self.assertRaises(ValueError):audit_plan(plan)


if __name__=="__main__":unittest.main()
