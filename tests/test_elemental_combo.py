import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from elemental_combo import ComboRules,Hit

class ComboTests(unittest.TestCase):
    def setUp(self):
        self.c=ComboRules();self.c.start_run('run')
    def hit(self,n,**kw):
        values=dict(run='run',owner='a',weapon='w',target='enemy',attack=str(n),time=n/10)
        values.update(kw);return self.c.hit(Hit(**values))
    def test_next_attack_after_n(self):
        for n in range(3):self.assertEqual(self.hit(n),[])
        self.assertEqual(self.hit(3)[0]['element'],'magic')
    def test_duplicate_and_generated_damage_do_not_count(self):
        self.hit(0);self.hit(0);self.hit(1,direct=False);self.hit(2,damage=0)
        self.assertEqual(self.c.counters[('a','w')],1)
    def test_target_local_combination_and_clear(self):
        results=[self.hit(n) for n in range(12)]
        self.assertEqual(results[-1][-1]['kind'],'combo')
        self.assertEqual(results[-1][-1]['elements'],('fire','lightning','magic'))
        self.assertFalse(self.c.marks)
        self.assertGreater(self.c.cooldowns['enemy'],1.1)
    def test_expired_marks_do_not_combine(self):
        for n in range(12):out=self.hit(n,time=n*20)
        self.assertEqual(len(out),1)
    def test_targets_and_owners_do_not_share_marks(self):
        for n in range(8):self.hit(n)
        for n in range(8,12):out=self.hit(n,target='other')
        self.assertEqual(len(out),1)
        for n in range(12,24):out=self.hit(n,owner='b')
        self.assertEqual(out[-1]['kind'],'combo')
        self.assertNotIn(('a','enemy'),self.c.marks)
    def test_unequip_discards_charge(self):
        for n in range(3):self.hit(n)
        self.c.unequip('a','w');self.assertEqual(self.hit(3),[])
        self.assertEqual(self.hit(4,equipped=False),[])
    def test_run_reset_rejects_old_events(self):
        self.hit(0);self.c.start_run('new');self.assertEqual(self.hit(1),[])
        self.assertFalse(self.c.counters)
    def test_global_target_cooldown(self):
        for n in range(12):self.hit(n)
        for n in range(12,24):out=self.hit(n,owner='b')
        self.assertEqual(len(out),1)
        self.assertFalse(self.c.marks)
    def test_no_time_reversal(self):
        self.hit(10);self.hit(0);self.assertEqual(self.c.counters[('a','w')],1)
