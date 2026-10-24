import sys
import unittest
from pathlib import Path
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from relic_presets import Planner


def fixture():
    effects=[]
    for key,compat,allowed in [(1,1,"1"),(2,2,"1"),(3,1,"1"),(4,4,"0")]:
        effects.append({"ID":str(key),"Name":f"effect{key}","isDebuff":"0",
                        "allowIroneye":allowed,"compatibilityId":str(compat),"exclusivityId":"-1"})
    pools={str(i):[{"effect_id":i,"weight":1,"dlc_weight_raw":-1}] for i in range(1,5)}
    templates=[{"id":i,"name":"test","deep_raw":0,"pool_links":{
        "attachEffectTableId_1":i,"attachEffectTableId_2":-1,"attachEffectTableId_3":-1,
        "attachEffectTableId_curse1":-1}} for i in range(1,5)]
    return Planner({"effects":effects,"pools":pools,"templates":templates,"regulation_sha256":"test"},
                   {"normal":{"normal":2,"deep":0},"depths":{"1":{"normal":2,"deep":1}},
                    "catalog_policy":{"normal_template_ids":[1,2,3,4]}})


class Presets(unittest.TestCase):
    def test_unknown_and_wrong_class(self):
        p=fixture()
        for key in (999,4,True,"1"):
            draft=p.new();draft["normal_effects"]=[key]
            self.assertFalse(p.validate(draft)["valid_draft"])

    def test_budget_and_duplicate_and_group(self):
        p=fixture()
        for chosen in ([1,2,3],[1,1],[1,3]):
            draft=p.new();draft["normal_effects"]=chosen
            self.assertFalse(p.validate(draft)["valid_draft"])

    def test_version_and_normal_deep_separation(self):
        p=fixture();draft=p.new();draft["catalog_hash"]="stale"
        self.assertFalse(p.validate(draft)["valid_draft"])
        draft=p.new();draft["deep_templates"]=[1]
        self.assertFalse(p.validate(draft)["valid_draft"])

    def test_roundtrip_and_no_overwrite(self):
        from relic_presets import load
        p=fixture();draft=p.new();draft["normal_effects"]=[1,2]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"preset.json";p.save(draft,path)
            self.assertTrue(p.validate(load(path))["valid_draft"])
            self.assertFalse(p.validate(load(path))["game_applicable"])
            with self.assertRaises(FileExistsError):p.save(draft,path)

    def test_manifest_changes_only_links(self):
        p=fixture();draft=p.new();draft["normal_effects"]=[2]
        result=p.experimental_manifest(draft,1)
        self.assertEqual(result["changes"],[{"table":"EquipParamAntique","row_id":1,
            "field":"attachEffectTableId_1","before":1,"after":2}])

    def test_random_pool_cannot_be_compiled(self):
        p=fixture();draft=p.new();draft["normal_effects"]=[2]
        del p.fixed_pools[2]
        with self.assertRaises(ValueError):p.experimental_manifest(draft,1)

    def test_deep_missing_curse_rejected(self):
        p=fixture();p.templates[1]["deep_raw"]=1
        with self.assertRaises(ValueError):p.deep_effects(1)

    def test_random_template_requires_slot_membership(self):
        p=fixture()
        for e in p.effects.values():
            e["overrideBaseEffectId"]="1"
        p.templates[100]={"id":100,"deep_raw":0,"color_raw":3,"pool_links":{
            "attachEffectTableId_1":100,"attachEffectTableId_2":-1,"attachEffectTableId_3":-1}}
        for t in p.templates.values():
            t.setdefault("color_raw",0)
        p.catalog["pools"]["100"]=[{"effect_id":1,"weight":1,"dlc_weight_raw":-1}]
        self.assertEqual(p.native_slot_assignment([1],3)["template_id"],100)
        with self.assertRaises(ValueError):p.native_slot_assignment([2],3)
        p.catalog["pools"]["100"][0]["dlc_weight_raw"]=0
        with self.assertRaises(ValueError):p.native_slot_assignment([1],3)

    def test_deep_pair_cannot_drop_or_invent_curse(self):
        p=fixture()
        p.deep={1,2};p.curse_required={1};p.curse_free={2};p.curses={3}
        for bundle in ({"effect_id":1,"curse_id":None},{"effect_id":1,"curse_id":999},
                       {"effect_id":2,"curse_id":3}):
            draft=p.new(mode="deep",depth=1);draft["deep_bundles"]=[bundle]
            self.assertFalse(p.validate(draft)["valid_draft"])
        draft=p.new(mode="deep",depth=1);draft["deep_bundles"]=[{"effect_id":2,"curse_id":None}]
        self.assertTrue(p.validate(draft)["valid_draft"])
        with self.assertRaises(ValueError):p.experimental_manifest(draft,1)

    def test_loadout_requires_compatible_native_vessel(self):
        p=fixture();draft=p.new();draft["normal_effects"]=[1,2]
        with self.assertRaisesRegex(ValueError,"容器"):
            p.experimental_loadout_manifest(draft,[])

    def test_malformed_preset_rejected(self):
        p=fixture()
        for candidate in ([],None,{"schema_version":1}):
            self.assertFalse(p.validate(candidate)["valid_draft"])

    def test_deep_manifest_keeps_native_curse_slot(self):
        p=fixture();p.deep={1};p.curse_required={1};p.curses={2}
        p.effects[1]["overrideBaseEffectId"]="1"
        for t in p.templates.values():t["color_raw"]=0
        p.templates[100]={"id":100,"deep_raw":1,"color_raw":3,"pool_links":{
            "attachEffectTableId_1":2000000,"attachEffectTableId_2":-1,"attachEffectTableId_3":-1,
            "attachEffectTableId_curse1":3000000,"attachEffectTableId_curse2":-1,"attachEffectTableId_curse3":-1}}
        p.catalog["pools"]["2000000"]=[{"effect_id":1,"weight":1,"dlc_weight_raw":-1}]
        p.catalog["pools"]["3000000"]=[{"effect_id":2,"weight":1,"dlc_weight_raw":-1}]
        draft=p.new(mode="deep",depth=1);draft["deep_bundles"]=[{"effect_id":1,"curse_id":2}]
        result=p.experimental_deep_manifest(draft,3,{"ID":10041,"equipType":4,"equipId":1270})
        self.assertEqual(len(result["changes"]),3)
        self.assertTrue(any(c["field"]=="attachEffectTableId_curse1" and c["after"]==2 for c in result["changes"]))
        p.catalog["pools"]["3000000"][0]["weight"]=0
        with self.assertRaises(ValueError):p.experimental_deep_manifest(draft,3,{"ID":10041,"equipType":4,"equipId":1270})

if __name__=="__main__":
    unittest.main()
