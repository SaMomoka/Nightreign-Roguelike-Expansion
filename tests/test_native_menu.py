import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_menu import specification, decode_integer, SOURCE
import test_combined_package as combined_fixtures
from relic_launch import verify_package


class MenuSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(source_sha256=SOURCE,
            loadout_assignments=[dict(shop_row_id=10041, template_id=129, effect_ids=[7000000,7000100,7000200])],
            changes=[dict(table="ShopLineupParam", row_id=10041, field="equipId", after=129)])

    def test_generated_menu_uses_existing_shop_assignment(self):
        result = specification(self.manifest)["presets"][0]
        self.assertEqual((result["shop_row_id"], result["template_id"]), (10041,129))
        self.assertIn("普通", result["labels"]["zhocn"])

    def test_deep_preserves_curse_metadata(self):
        self.manifest["loadout_assignments"][0].update(kind="deep", curse_ids=[6830000])
        result = specification(self.manifest)["presets"][0]
        self.assertEqual(result["curse_ids"], [6830000])
        self.assertIn("深夜", result["labels"]["zhocn"])

    def test_missing_or_different_shop_link_rejected(self):
        for changes in ([], [dict(table="ShopLineupParam",row_id=10041,field="equipId",after=132)]):
            self.manifest["changes"] = changes
            with self.assertRaises(ValueError): specification(self.manifest)

    def test_duplicate_and_outside_rows_rejected(self):
        original = copy.deepcopy(self.manifest)
        self.manifest["loadout_assignments"] *= 2
        with self.assertRaises(ValueError): specification(self.manifest)
        for row in (9999,11000,True,10041.0):
            self.manifest = copy.deepcopy(original)
            self.manifest["loadout_assignments"][0]["shop_row_id"] = row
            with self.assertRaises(ValueError): specification(self.manifest)

    def test_bad_version_and_effect_count_rejected(self):
        self.manifest["source_sha256"] = "different"
        with self.assertRaises(ValueError): specification(self.manifest)
        self.manifest["source_sha256"] = SOURCE
        self.manifest["loadout_assignments"][0]["effect_ids"] = [1,2,3,4]
        with self.assertRaises(ValueError): specification(self.manifest)

    def test_integer_expressions_match_native_shop_arguments(self):
        self.assertEqual(decode_integer("8210270000A1"),10000)
        self.assertEqual(decode_integer("82F72A0000A1"),10999)
        for invalid in ("8210270000","0010270000A1","41A1"):
            with self.assertRaises(ValueError): decode_integer(invalid)


class NativeMenuPackageTests(unittest.TestCase):
    def test_native_assets_are_required_and_profile_is_exact(self):
        fixture = combined_fixtures.CombinedPackageTests()
        fixture.setUp()
        self.addCleanup(fixture.temp.cleanup)
        fixture.meta["kind"] = "native_menu"
        fixture.replace("generate.me3", fixture.common + '[[packages]]\nid = "NRE-Native-Menu"\nsource = "./mod"\n')
        names = ("menu-spec.json", "native-menu-report.json",
                 "mod/script/talk/m10_00_00_00.talkesdbnd.dcx",
                 "mod/msg/zhocn/menu_dlc01.msgbnd.dcx","mod/msg/engus/menu_dlc01.msgbnd.dcx")
        with self.assertRaises(ValueError): verify_package(fixture.folder, fixture.root)
        for name in names:
            (fixture.folder / name).parent.mkdir(parents=True, exist_ok=True)
            fixture.replace(name, "test-only")
        self.assertEqual(verify_package(fixture.folder,fixture.root)["kind"],"native_menu")
        fixture.replace("generate.me3", fixture.common + '[[packages]]\nid = "NRE-Native-Menu"\nsource = "./reward-mod"\n')
        with self.assertRaises(ValueError): verify_package(fixture.folder,fixture.root)


if __name__ == "__main__":
    unittest.main()
