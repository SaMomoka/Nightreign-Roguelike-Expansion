import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from numeric_reward import extra_entries,redemption_events,TOKEN_GOODS,EVENT_BASE

class NumericRewardTests(unittest.TestCase):
    def test_spell_damage_is_separated_from_damage_type(self):
        entries=extra_entries(6)
        magic,sorcery,prayer=entries[:3]
        self.assertEqual(magic['fields']['fireAttackRate'],1)
        self.assertEqual(sorcery['fields']['miracleParamChange'],0)
        self.assertEqual(prayer['fields']['magParamChange'],0)
        self.assertEqual(prayer['fields']['miracleParamChange'],1)
        self.assertNotIn('motionInterval',str(entries))

    def simulate_dispatch(self,flags,tokens):
        entries=extra_entries(6);events=redemption_events(entries)
        code=next(x['instructions'] for x in events if x['id']==EVENT_BASE)
        # Start after the initial request wait. Inputs represent flags raised
        # while the single native dispatcher was waiting.
        pc=next(i for i,x in enumerate(code) if (x['bank'],x['id'])==(3,4))
        awards=[];owns=False
        while pc<len(code):
            x=code[pc];op=x['bank'],x['id'];raw=bytes.fromhex(x['hex']);pc+=1
            if op==(3,4):owns=tokens>0
            elif op==(1000,2):
                if not owns:break
            elif op==(1003,1):
                skip,state,typ,flag=struct.unpack('<BBBxI',raw)
                if flag not in flags:pc+=skip
            elif op==(2003,24):tokens-=struct.unpack('<B3xii',raw)[2]
            elif op==(2003,107):awards.append(struct.unpack('<i',raw)[0])
            elif op==(1000,4):break
            else:self.fail('Unexpected dispatcher instruction')
        return tokens,awards,entries

    def test_one_token_cannot_redeem_two_requested_choices(self):
        tokens,awards,entries=self.simulate_dispatch({10009900,10009901},1)
        self.assertEqual(tokens,0);self.assertEqual(awards,[entries[0]['redeem_lot']])

    def test_without_token_no_reward(self):
        tokens,awards,_=self.simulate_dispatch({10009900},0)
        self.assertEqual((tokens,awards),(0,[]))

    def test_cancel_does_not_consume_token(self):
        tokens,awards,_=self.simulate_dispatch(set(),1)
        self.assertEqual((tokens,awards),(1,[]))

    def test_owned_ids_are_distinct_and_packable(self):
        entries=extra_entries(6);redemption_events(entries)
        ids=[e['goods_id'] for e in entries]+[TOKEN_GOODS]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(0<x<=0xffffff for x in ids))

if __name__=='__main__':unittest.main()
