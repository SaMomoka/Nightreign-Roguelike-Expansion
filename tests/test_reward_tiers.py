import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from phase1_rewards import compile_manifest
from reward_tiers import BASE, probability_report


def fixture():
    config=json.loads((ROOT/"data/phase1_native_buffs.json").read_text(encoding="utf-8"))
    tables={n:[] for n in ("ItemTableParam","EquipParamGoods","PermanentBuffParam","SpEffectParam","ItemLotParam_enemy")}
    normals=((8000000,8010000,8010100,8020000,8020200),
             (8100000,8100500,8120000,8330103),(8200000,8200500,8210700,8230000))
    rares=((8000001,8010001,8010101,8020001,8020201),
           (8100001,8100501,8120001,8330104),(8200001,8200501,8210701,8230001))
    def poolrow(pool,item,category="1"):
        return dict(ID=str(pool),itemCategory=category,itemId=str(item),chanceWeight="100",
                    quantity="1",onlyForClass="0",eventFlagId="0",disableParam_NT="1",unknown_6="-1",unknown_7="1")
    tables["ItemTableParam"].append(poolrow(1200600,4200100,"7"))
    for tier,pools in enumerate((normals,rares)):
        for group,ids in enumerate(pools):
            pool=(4200101 if tier==0 else 4200301)+group
            for item in ids:
                tables["ItemTableParam"].append(poolrow(pool,item))
                tables["EquipParamGoods"].append(dict(ID=str(item),goodsType="11",vagrantItemLotId=str(item)))
                tables["PermanentBuffParam"].append(dict(ID=str(item),spEffectId=str(item)))
                fields=next((b["effect_fields"] for b in config["buffs"] if b["goods_id"]==item),{})
                tables["SpEffectParam"].append(dict(ID=str(item),**{k:str(v) for k,v in fields.items()}))
    for index in range(3):
        row=dict(ID=str(6000050+index))
        for slot in range(1,9):
            suffix="%02d"%slot
            row.update({"lotItemId"+suffix:str(4200100 if index==2 else 7900050),
                        "lotItemCategory"+suffix:"7",
                        "lotItemBasePoint"+suffix:"100" if slot<=((5,2,1)[index]) else "0"})
        tables["ItemLotParam_enemy"].append(row)
    return config,tables


class TieredRewards(unittest.TestCase):
    def setUp(self):
        self.config,self.tables=fixture()

    def test_actual_native_plan_keeps_original_pools_untouched(self):
        original=copy.deepcopy(self.tables)
        plan=compile_manifest(self.config,self.tables,"tiered_choices")
        self.assertEqual(self.tables,original)
        self.assertEqual(len(plan["additions"]),32)
        self.assertEqual(len(plan["changes"]),8)
        self.assertTrue(all(c["table"]=="ItemLotParam_enemy" for c in plan["changes"]))
        self.assertEqual(plan["allocated_pool_ids"],list(range(BASE,BASE+9)))
        self.assertEqual([f["native_members"] for f in plan["choice_families"]],[10,8,8])

    def test_exact_rarity_mass_and_probability_normalization(self):
        plan=compile_manifest(self.config,self.tables,"tiered_choices")
        common={8000000,8010000,8010100,8020000,8020200,8100000,8100500,8120000,8330103,
                8200000,8200500,8210700,8230000}
        for distribution in plan["probability_report"].values():
            total=sum(Fraction(v["numerator"],v["denominator"]) for v in distribution.values())
            normal=sum(Fraction(v["numerator"],v["denominator"]) for k,v in distribution.items() if int(k) in common)
            self.assertEqual(total,1)
            self.assertEqual(normal,Fraction(3,4))

    def test_zero_one_tier_is_supported_but_both_zero_are_rejected(self):
        self.config["rarity_weights"]={"normal":0,"rare":100}
        plan=compile_manifest(self.config,self.tables,"tiered_choices")
        self.assertEqual(len(plan["probability_report"][BASE]),5)
        self.assertNotIn("8000000",plan["probability_report"][BASE])
        self.config["rarity_weights"]={"normal":0,"rare":0}
        with self.assertRaises(ValueError):compile_manifest(self.config,self.tables,"tiered_choices")

    def test_reject_allocation_collision(self):
        self.tables["ItemTableParam"].append(dict(self.tables["ItemTableParam"][0],ID=str(BASE)))
        with self.assertRaises(ValueError):compile_manifest(self.config,self.tables,"tiered_choices")

    def test_reject_unreviewed_reference_template(self):
        self.tables["ItemTableParam"][0]["eventFlagId"]="123"
        with self.assertRaises(ValueError):compile_manifest(self.config,self.tables,"tiered_choices")

    def test_reject_cycle_missing_target_empty_and_dormant_cycle(self):
        cases=[
            {1:[dict(category=7,target=1,weight=1)]},
            {1:[dict(category=7,target=2,weight=1)]},
            {1:[dict(category=1,target=100,weight=0)]},
            {1:[dict(category=1,target=100,weight=1),dict(category=7,target=1,weight=0)]},
        ]
        for graph in cases:
            with self.subTest(graph=graph):
                with self.assertRaises(ValueError):probability_report(graph,[1])

    def test_nested_paths_combine_same_good_probability_exactly(self):
        graph={1:[dict(category=7,target=2,weight=1),dict(category=7,target=3,weight=2)],
               2:[dict(category=1,target=100,weight=1)],
               3:[dict(category=1,target=100,weight=1),dict(category=1,target=200,weight=1)]}
        result=probability_report(graph,[1])[1]
        self.assertEqual((result["100"]["numerator"],result["100"]["denominator"]),(2,3))

    def test_reject_unsupported_rarity_or_non_integer_weight(self):
        for weights in ({"normal":True,"rare":25},{"normal":75,"rare":1.5},
                        {"normal":75,"rare":-1},{"normal":75,"rare":65536},{"normal":75,"gold":25}):
            with self.subTest(weights=weights):
                self.config["rarity_weights"]=weights
                with self.assertRaises(ValueError):compile_manifest(self.config,self.tables,"tiered_choices")

    def test_reject_cross_family_alias_across_rarities(self):
        # Rare defense must not resolve to a common survival effect.
        row=next(r for r in self.tables["PermanentBuffParam"] if r["ID"]=="8200001")
        row["spEffectId"]="8000000"
        with self.assertRaises(ValueError):compile_manifest(self.config,self.tables,"tiered_choices")


if __name__=="__main__":
    unittest.main()
