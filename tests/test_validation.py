import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tools"/(name+".py"))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
v=module("validate")
d=module("diff_csv")

class Validation(unittest.TestCase):
    def setUp(self):
        self.b=v.read(ROOT/"data/buffs.json")
        self.r=v.read(ROOT/"data/rules.json")
        self.m=v.read(ROOT/"integration/mappings.json")
    def errors(self):
        return v.validate(self.b,self.r,self.m)
    def test_catalog_valid(self):
        self.assertEqual(self.errors(),[])
    def test_all_requirements_retained(self):
        self.assertEqual({b["id"] for b in self.b["buffs"]},{f"BUFF-{n:03}" for n in range(1,16)})
    def test_duplicate_id(self):
        self.b["buffs"].append(copy.deepcopy(self.b["buffs"][0]))
        self.assertIn("duplicate buff ID", self.errors())
    def test_unknown_reference(self):
        self.b["buffs"][0]["required_buffs"]=["BUFF-999"]
        self.assertTrue(any("bad reference" in e for e in self.errors()))
    def test_dependency_cycle(self):
        self.b["buffs"][0]["prerequisites"]=["BUFF-002"]
        self.b["buffs"][1]["prerequisites"]=["BUFF-001"]
        self.assertIn("prerequisite cycle", self.errors())
    def test_transitive_exclusion(self):
        self.b["buffs"][0]["prerequisites"]=["BUFF-004"]
        self.b["buffs"][3]["prerequisites"]=["BUFF-005"]
        self.b["buffs"][0]["exclusions"]=["BUFF-005"]
        self.assertTrue(any("excluded transitive" in e for e in self.errors()))
    def test_negative_weight(self):
        self.b["buffs"][0]["base_weight"]=-1
        self.assertTrue(any("invalid weight" in e for e in self.errors()))
    def test_unique_cap(self):
        self.b["buffs"][0]["max_stacks"]=2
        self.assertTrue(any("unique buff" in e for e in self.errors()))
    def test_trigger_cycle(self):
        self.r["synergies"][0]["emits"]="heartsteel_growth"
        self.assertIn("trigger chain cycle", self.errors())
    def test_consumable_recursion(self):
        self.b["buffs"][9]["parameters"]["returned_m"]=4
        self.assertIn("consumable infinite loop", self.errors())
    def test_empty_rarity_weights(self):
        self.r["rarity_weights"]={k:0 for k in self.r["rarity_weights"]}
        self.assertIn("rarity weights invalid", self.errors())
    def test_release_fails_closed(self):
        self.assertTrue(v.validate(self.b,self.r,self.m,True))
    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"bad.json"; p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError): v.read(p)

class CsvDiff(unittest.TestCase):
    def test_single_field_and_row_order(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/"a.csv",Path(folder)/"b.csv"
            a.write_text("ID,maxHpRate\n1,1.1\n2,1.0\n")
            b.write_text("ID,maxHpRate\n2,1.0\n1,1.15\n")
            result=d.compare(a,b,"ID")
            self.assertEqual(result["changes"],[{"row":"1","field":"maxHpRate","before":"1.1","after":"1.15"}])
    def test_duplicate_rows_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/"a.csv"; a.write_text("ID,value\n1,a\n1,b\n")
            with self.assertRaises(ValueError): d.load(a,"ID",",")
    def test_schema_change_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/"a.csv",Path(folder)/"b.csv"
            a.write_text("ID,value\n1,a\n"); b.write_text("ID,other\n1,a\n")
            with self.assertRaises(ValueError): d.compare(a,b,"ID")

if __name__=="__main__":
    unittest.main()
