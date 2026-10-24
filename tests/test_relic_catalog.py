import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("relic_catalog", Path(__file__).resolve().parents[1] / "tools/relic_catalog.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RelicEvidence(unittest.TestCase):
    def test_unique_tables_reject_duplicate(self):
        with self.assertRaises(ValueError):
            m.unique_index([{"ID": "1"}, {"ID": "1"}])

    def test_csv_rejects_missing_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "a.csv"
            p.write_text("ID,Name\n1,a\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                m.read_table(p, ["ID", "chanceWeight"])

    def test_csv_preserves_duplicate_pool_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "a.csv"
            p.write_text("ID,attachEffectId\n100,1\n100,2\n", encoding="utf-8")
            rows = m.read_table(p, ["ID", "attachEffectId"])
            self.assertEqual(len(rows), 2)
            self.assertEqual([r["attachEffectId"] for r in rows], ["1", "2"])

    def test_unresolved_pool_rejected(self):
        catalog = {"templates": [{"id": 1, "pool_links": {"positive": 42}}], "pools": {}}
        with self.assertRaises(ValueError):
            m.inspect_template(catalog, 1)

    def test_inspection_never_claims_applicable(self):
        catalog = {"templates": [{"id": 1, "pool_links": {"positive": 42, "negative": -1}}],
                   "pools": {"42": [{"effect_id": 2, "weight": 10},
                                     {"effect_id": 3, "weight": 0},
                                     {"effect_id": 2, "weight": 1}]}}
        result = m.inspect_template(catalog, 1)
        self.assertEqual(result["status"], "draft_not_applicable")
        self.assertEqual(result["slots"][0]["candidate_rows"], 3)
        self.assertEqual(result["slots"][0]["base_positive_weight_effects"], [2])

    def test_wrong_regulation_rejected_before_csv_load(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "regulation.bin"
            p.write_bytes(b"wrong version")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                m.build_catalog(temp, p)


if __name__ == "__main__":
    unittest.main()
