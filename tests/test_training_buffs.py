import json,struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from training_buff_menu import catalog,compile_menu,encode_pool,MAGIC
from training_buff_package import audit,event_plan
from training_buff_runtime import consumed_response

class TrainingBuffTests(unittest.TestCase):
    def setUp(self):self.entries=catalog(json.loads((ROOT/'data/phase1_native_buffs.json').read_text(encoding='utf-8')))
    def test_slots_have_all_candidates_and_native_controls(self):
        p=compile_menu(self.entries);audit(p)
        self.assertEqual(len(p['labels']),36)
        self.assertEqual(len(set(e['goods_id'] for e in self.entries)),12)
        for slot in range(3):
            self.assertEqual(sum(s['name'].startswith(f'select{slot}_') and not s['name'].endswith('_ack') for s in p['states']),12)
    def test_original_settings_and_exit_retained(self):
        p=compile_menu(self.entries)
        self.assertEqual(next(x for x in p['states'] if x['name']=='original')['template'],'original')
        self.assertEqual(next(x for x in p['states'] if x['name']=='exit')['conditions'][0]['target'],2)
    def test_pool_changes_only_item_reference_for_all_candidates(self):
        original=bytes(range(36))
        for e in self.entries:
            b=encode_pool(original,8,e['goods_id'])
            self.assertEqual(b[:8],original[:8]);self.assertEqual(b[12:],original[12:])
            self.assertEqual(struct.unpack_from('<i',b,8)[0],e['goods_id'])
        for n in (-1,0,12345):
            with self.assertRaises(ValueError):encode_pool(original,8,n)
    def test_changed_layout_rejected(self):
        with self.assertRaises(ValueError):encode_pool(bytes(48),8,8000000)
        with self.assertRaises(ValueError):encode_pool(bytes(36),12,8000000)
    def test_menu_busy_cycle_rejected(self):
        p=compile_menu(self.entries);s=p['states'][0];s['conditions']=[dict(target=s['id'],eval='41a1')]
        with self.assertRaises(ValueError):audit(p)
    def test_native_consumption_requires_changed_valid_request(self):
        b=lambda *v:struct.pack('<4i',*v)
        old=b(MAGIC,10,0,0)
        self.assertTrue(consumed_response(old,b(MAGIC,11,0,0)))
        self.assertFalse(consumed_response(old,old))
        self.assertFalse(consumed_response(old,b(MAGIC+1,11,0,0)))
        self.assertFalse(consumed_response(old,b(MAGIC,999,0,0)))
        self.assertFalse(consumed_response(old,b(MAGIC,11,0,1)))
    def test_drop_moves_carrier_to_player_before_spawning(self):
        events=event_plan()
        warp=next(i for i,e in enumerate(events) if (e['bank'],e['id'])==(2004,42))
        drop=next(i for i,e in enumerate(events) if (e['bank'],e['id'])==(2004,37))
        self.assertEqual(struct.unpack('<IB3xIiI',bytes.fromhex(events[warp]['hex'])),(10000980,2,10000,-1,10000))
        self.assertLess(warp,drop)
        self.assertEqual((events[warp+1]['bank'],events[warp+1]['id']),(1001,1))

    def test_event_targets_only_owned_carrier(self):
        events=event_plan();drop=[e for e in events if (e['bank'],e['id'])==(2004,37)]
        self.assertEqual(len(drop),1);self.assertEqual(struct.unpack('<I',bytes.fromhex(drop[0]['hex']))[0],10000980)

if __name__=='__main__':unittest.main()
