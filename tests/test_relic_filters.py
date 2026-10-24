import copy
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from relic_filters import bind_filters, groups, product_index, color_products
from relic_selection import RelicSelection
from full_relic_menu import compile_menu, SHOP_BASE
from relic_runtime import Dispatcher
from test_relic_selection import fixture


class NativeFilterCrafting(unittest.TestCase):
    def setUp(self):
        self.catalog=fixture()
        for e in self.catalog['entries']:
            e['filter']=dict(category=30,subcategory=30000,family=e['effect_id']//2,
                category_names={'zhocn':'全部'},subcategory_names={'zhocn':'能力值'})
        self.plan=compile_menu(self.catalog)

    def test_two_visible_entries_and_six_editor_actions(self):
        self.assertEqual(self.plan['visible_editors'],[0,2])
        by_name={s['name']:s for s in self.plan['states']}
        self.assertEqual(len(by_name['select_items']['entry']),3)
        for editor in (0,2):
            self.assertEqual(len(by_name[f'editor{editor}_dispatch']['conditions']),7)
        self.assertFalse(any('遗物 1' in t['zhocn'] or '遗物 2' in t['zhocn'] for t in self.plan['texts']))
        self.assertNotIn('editor1',by_name)
        self.assertNotIn('editor3',by_name)

    def test_filter_partition_preserves_all_effects_and_unknowns(self):
        self.catalog['entries'][0]['filter']=None
        model=RelicSelection(self.catalog)
        for editor,negative in ((0,False),(2,False),(2,True)):
            result=groups(model,editor,negative)
            effects=[e for c in result.values() for sub in c['subcategories'].values() for family in sub['families'].values() for e in family]
            self.assertEqual(sorted(effects),model.candidates(editor,negative))
            self.assertEqual(len(effects),len(set(effects)))
        self.assertIn(-1,groups(model,0))

    def test_every_color_routes_to_distinct_native_product(self):
        prepared=[]
        def prepare(editor,request,entries):
            prepared.append(copy.deepcopy(request))
            return SHOP_BASE+product_index(editor,request['color'])
        d=Dispatcher(self.catalog,self.plan,prepare)
        for editor,effects in ((0,(1,2,3)),(2,(12,13,14))):
            for slot,effect in enumerate(effects):d.dispatch(200+editor*3+slot,effect)
            for color in range(4):
                d.dispatch(600+editor,color)
                self.assertEqual(d.dispatch(700+editor,0),self.plan['color_labels'][str(color)])
                self.assertEqual(d.dispatch(500+editor,0),SHOP_BASE+product_index(editor,color))
        self.assertEqual([r['color'] for r in prepared],list(range(4))*2)
        self.assertEqual(len({product_index(e,c) for e in (0,2) for c in range(4)}),8)

    def test_color_change_invalidates_prepared_request_and_preserves_effects(self):
        m=RelicSelection(self.catalog)
        for slot,effect in enumerate((1,2,3)):m.choose_positive(0,slot,effect)
        draft=copy.deepcopy(m.drafts[0]);old=m.request(0)
        m.choose_color(0,0)
        self.assertEqual(m.drafts[0],draft)
        with self.assertRaises(ValueError):m.verify_ack(dict(old,runtime_verified=True,shop_id=SHOP_BASE))
        self.assertEqual(m.colors[2],3)
        for bad in (-1,4,True,'red'):
            with self.assertRaises(ValueError):m.choose_color(0,bad)

    def test_native_pages_fit_and_all_targets_exist(self):
        ids={s['id'] for s in self.plan['states']}|{10}
        for state in self.plan['states']:
            self.assertTrue(all(c['target'] in ids for c in state['conditions']))
            self.assertLessEqual(sum(c['id']==149 for c in state['entry']),9)

    def test_filter_binding_uses_native_id_not_keyword_matching(self):
        cat={'source_sha256':'pinned','entries':[{'effect_id':7}]}
        native={'source_sha256':'pinned','tables':{
            'AttachEffectParam':[{'ID':7,'attachFilterParamId':42}],
            'AttachEffectFilterParam':[{'ID':42,'disableParam_NT':0,'attachEffectFilterCategory':100}],
            'AttachEffectFilterSubCategoryParam':[{'ID':100,'filterCategory':10,'textId':2}],
            'AttachEffectFilterCategoryParam':[{'ID':10,'textId':1}]},
            'languages':{'zhocn':{'1':'角色','2':'追踪者'}}}
        self.assertEqual(bind_filters(cat,native)['entries'][0]['filter']['family'],42)
        native['source_sha256']='other'
        with self.assertRaises(ValueError):bind_filters(cat,native)

    def test_pending_negative_survives_rejected_color_change(self):
        m=RelicSelection(self.catalog);m.choose_positive(2,0,10)
        with self.assertRaises(ValueError):m.choose_color(2,1)
        m.choose_negative(20)
        self.assertEqual(m.drafts[2][0],dict(effect_id=10,curse_id=20))

    def test_colored_template_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):product_index(1,0)
        with self.assertRaises(ValueError):product_index(2,True)
        native={'tables':{'EquipParamAntique':[dict(ID=102,relicColor=1,isDeepRelic=0,attachEffectTableId_3=100)]}}
        with self.assertRaises(ValueError):color_products(native)

if __name__=='__main__':unittest.main()
