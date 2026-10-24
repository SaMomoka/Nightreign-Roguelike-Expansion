import copy
import json
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from phase1_rewards import compile_manifest, audit_choice_families, audit_reward_scope
from relic_launch import verify_package, sha


class RewardAdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "data/phase1_native_buffs.json").read_text(encoding="utf-8"))
        self.tables = {name: [] for name in ("ItemTableParam", "EquipParamGoods",
                                           "PermanentBuffParam", "SpEffectParam", "ItemLotParam_enemy")}
        for entry in self.config["buffs"]:
            rid = str(entry["goods_id"])
            self.tables["ItemTableParam"].append(dict(ID="4200100", itemCategory="1", itemId=rid,
                chanceWeight="100", quantity="1", onlyForClass="0", eventFlagId="0",
                disableParam_NT="1", unknown_6="-1", unknown_7="1"))
            self.tables["EquipParamGoods"].append(dict(ID=rid, goodsType="11", vagrantItemLotId=rid))
            self.tables["PermanentBuffParam"].append(dict(ID=rid, spEffectId=rid))
            self.tables["SpEffectParam"].append(dict(ID=rid, **{k: str(v) for k,v in entry["effect_fields"].items()}))
        for source in list(self.tables["ItemTableParam"]):
            row=copy.deepcopy(source)
            goods_id=int(row["itemId"])
            row["ID"]=str(4200101 if goods_id in (8000000,8010000,8020000) else
                          4200102 if goods_id==8100000 else 4200103)
            self.tables["ItemTableParam"].append(row)
        for row_id in (6000050, 6000051, 6000052):
            row = dict(ID=str(row_id))
            for slot in range(1,9):
                s = "%02d" % slot
                row.update({"lotItemId"+s: str(4200100 if row_id==6000052 else 7900050),
                            "lotItemCategory"+s:"7", "lotItemBasePoint"+s:"100" if slot==1 else "0"})
            self.tables["ItemLotParam_enemy"].append(row)

    def test_pool_duplicate_ids_preserve_distinct_ordinal_and_guards(self):
        manifest = compile_manifest(self.config, self.tables)
        self.assertEqual(len({c["row_ordinal"] for c in manifest["changes"]}),6)
        self.assertEqual({c["guard"]["itemId"] for c in manifest["changes"]},
                         {e["goods_id"] for e in self.config["buffs"]})

    def test_does_not_mutate_native_effects_or_input_tables(self):
        original = copy.deepcopy(self.tables)
        manifest = compile_manifest(self.config, self.tables, "three_choices_probe")
        self.assertEqual(self.tables, original)
        self.assertTrue(all(c["field"]=="chanceWeight" or c["field"].startswith("lotItemId") for c in manifest["changes"]))
        self.assertFalse(any(c["row_id"]==6000052 for c in manifest["changes"]))

    def test_reject_broken_reference_even_if_names_match(self):
        self.tables["EquipParamGoods"][0]["vagrantItemLotId"]="999"
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables)

    def test_reject_ambiguous_member(self):
        self.tables["ItemTableParam"].append(copy.deepcopy(self.tables["ItemTableParam"][0]))
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables)

    def test_reject_changed_effect_semantics(self):
        self.tables["SpEffectParam"][0]["maxHpRate"]="1.5"
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables)

    def test_reject_zero_negative_overflow_boolean_fractional_weights(self):
        for value in (0,-1,65536,True,1.5):
            with self.subTest(value=value):
                self.config["buffs"][0]["weight"]=value
                with self.assertRaises(ValueError): compile_manifest(self.config,self.tables)

    def test_reject_non_table_route(self):
        self.tables["ItemLotParam_enemy"][0]["lotItemCategory01"]="1"
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables,"three_choices_probe")

    def test_reject_unreviewed_pool_or_mode(self):
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables,"automatic_grant")
        self.config["pool_id"]=100
        with self.assertRaises(ValueError): compile_manifest(self.config,self.tables)

    def test_distinct_choices_use_disjoint_effects_and_all_three_routes(self):
        manifest=compile_manifest(self.config,self.tables,"distinct_choices")
        self.assertEqual(manifest["choice_uniqueness"],"DISJOINT_NATIVE_POOLS")
        self.assertEqual([f["native_members"] for f in manifest["choice_families"]],[3,1,2])
        routes={c["row_id"]:c["after"] for c in manifest["changes"] if c["table"]=="ItemLotParam_enemy"}
        self.assertEqual(routes,{6000050:4200101,6000051:4200102,6000052:4200103})
        self.assertTrue(all(c["row_id"]!=4200100 for c in manifest["changes"]))
        self.assertFalse(manifest["choice_layout_game_verified"])

    def test_reject_same_effect_under_different_goods(self):
        self.tables["PermanentBuffParam"][3]["spEffectId"]="8000000"
        with self.assertRaises(ValueError): audit_choice_families(self.tables)

    def test_reject_overlapping_or_conditional_family(self):
        original=copy.deepcopy(self.tables)
        overlap=copy.deepcopy(self.tables["ItemTableParam"][6])
        overlap["ID"]="4200102"
        self.tables["ItemTableParam"].append(overlap)
        with self.assertRaises(ValueError): audit_choice_families(self.tables)
        self.tables=original
        self.tables["ItemTableParam"][6]["onlyForClass"]="3"
        with self.assertRaises(ValueError): audit_choice_families(self.tables)

    def test_reject_empty_family(self):
        self.tables["ItemTableParam"]=[r for r in self.tables["ItemTableParam"] if r["ID"]!="4200103"]
        with self.assertRaises(ValueError): audit_choice_families(self.tables)

    def test_scope_counts_references_without_claiming_all_scripts(self):
        scope=audit_reward_scope(self.tables,(4200100,))
        # Even zero-weight references are reported, not silently assumed dead.
        self.assertEqual(scope["before_patch"][0]["enemy_lot_reference_count"],8)
        self.assertIn("not an exhaustive",scope["scope"])
        self.assertEqual(scope["fort_base_npcs"],[])

    def test_native_package_cannot_select_arbitrary_profile_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/"local/packages/test"
            (folder/"mod").mkdir(parents=True)
            common='profileVersion = "v1"\nsavefile = "NRE_test.sl2"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
            (folder/"play.me3").write_text(common,encoding="utf-8")
            (folder/"generate.me3").write_text(common+'[[packages]]\nid = "NRE-Native-Rewards"\nsource = "./mod"\n',encoding="utf-8")
            (folder/"mod/regulation.bin").write_bytes(b"fixture")
            (folder/"manifest.json").write_text("{}",encoding="utf-8")
            meta=dict(schema_version=1,kind="native_rewards",savefile="NRE_test.sl2",
                      sha256={n:sha(folder/n) for n in ("play.me3","generate.me3","mod/regulation.bin","manifest.json")})
            (folder/"package.json").write_text(json.dumps(meta),encoding="utf-8")
            self.assertEqual(verify_package(folder,root)["kind"],"native_rewards")
            for kind in ("relic","arbitrary"):
                meta["kind"]=kind
                (folder/"package.json").write_text(json.dumps(meta),encoding="utf-8")
                with self.assertRaises(ValueError):verify_package(folder,root)


if __name__=="__main__":
    unittest.main()
