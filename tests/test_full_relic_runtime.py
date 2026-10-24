import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from full_relic_menu import compile_menu,work,SHOP_BASE
from relic_runtime import Dispatcher,row_bytes
from relic_filters import product_index
from test_relic_selection import fixture


class FullRuntimeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.catalog=fixture()
        for e in self.catalog["entries"]:e["deterministic_pool"]=100000+e["effect_id"]
        self.plan=compile_menu(self.catalog)
        self.prepared=[]
        def prepare(editor,request,entries):
            self.prepared.append(request)
            return SHOP_BASE+product_index(editor,request['color'])
        self.dispatcher=Dispatcher(self.catalog,self.plan,prepare)

    def test_full_compiler_has_only_defined_native_work_indices(self):
        with self.assertRaises(ValueError):work(4)
        for state in self.plan["states"]:
            for c in state["entry"]:
                if c["id"]==100:
                    index=struct.unpack("<i",bytes.fromhex(c["args"][0])[1:5])[0]
                    self.assertIn(index,range(4))

    def test_all_state_targets_resolve(self):
        ids={s["id"] for s in self.plan["states"]}|{10}
        self.assertEqual(len(ids),len(self.plan["states"])+1)
        self.assertTrue(all(c["target"] in ids for s in self.plan["states"] for c in s["conditions"]))

    def test_all_three_complete_slots_prepare_one_native_shop(self):
        for slot,effect in enumerate((1,2,3)):
            self.assertEqual(self.dispatcher.dispatch(200+slot,effect),1)
        self.assertEqual(self.dispatcher.dispatch(500,0),SHOP_BASE+3)
        self.assertEqual(len(self.prepared),1)
        self.assertEqual(self.prepared[0]["price"],1)

    def test_incomplete_request_cannot_call_preparer(self):
        with self.assertRaises(ValueError):self.dispatcher.dispatch(500,0)
        self.assertEqual(self.prepared,[])

    def test_negative_reply_cannot_cross_editor_or_slot(self):
        self.assertEqual(self.dispatcher.dispatch(206,10),2)
        with self.assertRaises(ValueError):self.dispatcher.dispatch(309,20)
        self.assertEqual(self.dispatcher.dispatch(306,20),1)
        self.assertEqual(self.dispatcher.model.drafts[2][0]["curse_id"],20)

    def test_native_labels_update_and_free_effect_drops_negative(self):
        empty=self.dispatcher.dispatch(106,0)
        self.dispatcher.dispatch(206,10);self.dispatcher.dispatch(306,20)
        bound=self.dispatcher.dispatch(106,0)
        self.dispatcher.dispatch(206,12)
        free=self.dispatcher.dispatch(106,0)
        self.assertEqual(len({empty,bound,free}),3)
        self.assertIsNone(self.dispatcher.model.drafts[2][0]["curse_id"])

    def test_param_preparation_changes_only_six_declared_fields(self):
        original=bytes(range(48))
        entries={e["effect_id"]:e for e in self.catalog["entries"]}
        bundles=[dict(effect_id=10,curse_id=20),dict(effect_id=12,curse_id=None),dict(effect_id=13,curse_id=None)]
        offsets=[16,20,24,32,36,40]
        updated=row_bytes(original,offsets,bundles,entries)
        mutable={i for offset in offsets for i in range(offset,offset+4)}
        self.assertTrue(all(original[i]==updated[i] for i in range(48) if i not in mutable))
        self.assertEqual([struct.unpack_from("<i",updated,p)[0] for p in offsets],
                         [100010,100012,100013,100020,-1,-1])

    def test_layout_or_pool_uncertainty_rejects_preparation(self):
        with self.assertRaises(ValueError):row_bytes(bytes(48),[0,4,8,12,16,20],[],{})
        with self.assertRaises(ValueError):self.dispatcher.dispatch(999,0)
