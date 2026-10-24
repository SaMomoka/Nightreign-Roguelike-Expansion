import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from combined_package import inspect_inputs
from phase1_rewards import SOURCE
from relic_launch import sha, verify_package, launch


class CombinedPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "local/packages/combined_test"
        for sub in ("mod", "reward-mod", "inputs"):
            (self.folder / sub).mkdir(parents=True, exist_ok=True)
        self.common = 'profileVersion = "v1"\nsavefile = "NRE_combined_test.sl2"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
        files = {
            "generate.me3": self.common + '[[packages]]\nid = "NRE-Combined-Generation"\nsource = "./mod"\n',
            "play.me3": self.common + '[[packages]]\nid = "NRE-Native-Rewards"\nsource = "./reward-mod"\n',
            "rollback.me3": self.common,
            "manifest.json": json.dumps({"source_sha256": SOURCE}),
            "mod/regulation.bin": "combined-test-only",
            "reward-mod/regulation.bin": "rewards-test-only",
            "inputs/rewards.bin": "rewards-test-only",
            "inputs/relic.bin": "relic-test-only",
            "inputs/relic-manifest.json": "{}",
            "inputs/rewards-manifest.json": "{}",
            "mod/build-report.json": "{}",
        }
        for name, text in files.items():
            (self.folder / name).write_text(text, encoding="utf-8")
        self.meta = dict(schema_version=1, kind="combined", savefile="NRE_combined_test.sl2",
                         sha256={name: sha(self.folder / name) for name in files})
        self.save_meta()

    def save_meta(self):
        (self.folder / "package.json").write_text(json.dumps(self.meta), encoding="utf-8")

    def replace(self, name, text):
        (self.folder / name).write_text(text, encoding="utf-8")
        self.meta["sha256"][name] = sha(self.folder / name)
        self.save_meta()

    def test_three_profiles_share_save_and_verify(self):
        self.assertEqual(verify_package(self.folder, self.root)["kind"], "combined")

    def test_rehashed_play_cannot_keep_generation_mod(self):
        self.replace("play.me3", self.common + '[[packages]]\nid = "NRE-Native-Rewards"\nsource = "./mod"\n')
        with self.assertRaises(ValueError):
            verify_package(self.folder, self.root)

    def test_rollback_cannot_point_at_formal_save(self):
        self.replace("rollback.me3", self.common.replace("NRE_combined_test.sl2", "NR0000.sl2"))
        with self.assertRaises(ValueError):
            verify_package(self.folder, self.root)

    def test_reward_copy_must_match_frozen_input_even_if_rehashed(self):
        self.replace("reward-mod/regulation.bin", "not-the-selected-reward")
        with self.assertRaises(ValueError):
            verify_package(self.folder, self.root)

    def test_rollback_and_provenance_are_required(self):
        for name in ("rollback.me3", "inputs/rewards-manifest.json", "mod/build-report.json"):
            with self.subTest(name=name):
                old = self.meta["sha256"].pop(name)
                self.save_meta()
                with self.assertRaises(ValueError):
                    verify_package(self.folder, self.root)
                self.meta["sha256"][name] = old
        self.save_meta()

    def test_input_kind_source_and_table_restrictions(self):
        relic = {"source_sha256": SOURCE, "regulation_internal_version": "10350000",
                 "changes": [{"table": "EquipParamAntique"}]}
        reward = {"source_sha256": SOURCE, "regulation_internal_version": "10350000"}
        for bad in ("kind", "source", "table", "version"):
            with self.subTest(bad=bad):
                a = json.loads(json.dumps(relic))
                metadata = [{}, {"kind": "native_rewards"}]
                if bad == "kind": metadata[0]["kind"] = "combined"
                if bad == "source": a["source_sha256"] = "old"
                if bad == "table": a["changes"][0]["table"] = "ItemTableParam"
                if bad == "version": a["regulation_internal_version"] = "0"
                with patch("combined_package.verify_package", side_effect=metadata), \
                     patch("combined_package.read_json", side_effect=[a, reward]):
                    with self.assertRaises(ValueError):
                        inspect_inputs("a", "b", self.root)

    def test_generate_and_rollback_rejected_before_runtime_access(self):
        with self.assertRaises(ValueError):
            launch(self.folder, True, self.root, rollback=True)

    def test_actual_profile_selection_without_starting_process(self):
        with patch("relic_launch.load", wraps=lambda path: json.loads(Path(path).read_text(encoding="utf-8"))) as load:
            runtime = self.root / "local/runtime.json"
            fake_me3 = self.root / "me3.exe"
            fake_me3.write_bytes(b"test")
            game = self.root / "game"
            game.mkdir()
            (game / "regulation.bin").write_bytes(b"baseline")
            self.replace("manifest.json", json.dumps({"source_sha256": sha(game / "regulation.bin")}))
            runtime.write_text(json.dumps({"me3": str(fake_me3), "game": str(game),
                                          "test_seed": "NRE_seed.sl2"}), encoding="utf-8")
            for generation, rollback, label in ((True, False, "generate"), (False, False, "play"), (False, True, "rollback")):
                with patch("relic_launch.subprocess.run") as tasks, \
                     patch("relic_launch.subprocess.Popen") as process, \
                     patch("relic_launch.prepare_save", return_value=Path("NRE_combined_test.sl2")):
                    tasks.return_value.returncode = 0
                    tasks.return_value.stdout = b""
                    process.return_value.pid = 123
                    result = launch(self.folder, generation, self.root, rollback=rollback)
                    self.assertEqual(result["mode"], label)
                    self.assertEqual(process.call_args[0][0][-1], str(self.folder / (label + ".me3")))


if __name__ == "__main__":
    unittest.main()
