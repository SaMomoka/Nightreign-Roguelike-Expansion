import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from relic_launch import verify_package,prepare_save,sha


class LaunchIsolation(unittest.TestCase):
    def test_seed_copies_once_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            seed=Path(temp)/"NRE_seed.sl2";seed.write_bytes(b"baseline")
            dest=prepare_save(seed,"NRE_new.sl2")
            self.assertEqual(dest.read_bytes(),b"baseline")
            dest.write_bytes(b"progress")
            self.assertEqual(prepare_save(seed,"NRE_new.sl2").read_bytes(),b"progress")
            self.assertEqual(seed.read_bytes(),b"baseline")

    def test_formal_seed_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            seed=Path(temp)/"NR0000.sl2";seed.write_bytes(b"formal")
            with self.assertRaises(ValueError):prepare_save(seed,"NRE_new.sl2")
            seed=Path(temp)/"NRE_seed.sl2";seed.write_bytes(b"seed")
            for name in ("NR0000.sl2","../NRE_escape.sl2","NRE_seed.sl2"):
                with self.assertRaises(ValueError):prepare_save(seed,name)

    def test_package_hash_and_profile_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/"local/packages/test";(folder/"mod").mkdir(parents=True)
            common='profileVersion = "v1"\nsavefile = "NRE_test.sl2"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
            (folder/"play.me3").write_text(common,encoding="utf-8")
            (folder/"generate.me3").write_text(common+'[[packages]]\nid = "NRE-Relic-Generation"\nsource = "./mod"\n',encoding="utf-8")
            (folder/"mod/regulation.bin").write_bytes(b"test-only")
            (folder/"manifest.json").write_text("{}",encoding="utf-8")
            names=["play.me3","generate.me3","manifest.json","mod/regulation.bin"]
            meta={"schema_version":1,"savefile":"NRE_test.sl2","sha256":{n:sha(folder/n) for n in names}}
            (folder/"package.json").write_text(json.dumps(meta),encoding="utf-8")
            self.assertEqual(verify_package(folder,root)["savefile"],"NRE_test.sl2")
            (folder/"mod/regulation.bin").write_bytes(b"modified")
            with self.assertRaises(ValueError):verify_package(folder,root)
            meta["sha256"]["mod/regulation.bin"]=sha(folder/"mod/regulation.bin")
            (folder/"play.me3").write_text(common.replace("NRE_test.sl2","NR0000.sl2"),encoding="utf-8")
            meta["sha256"]["play.me3"]=sha(folder/"play.me3")
            (folder/"package.json").write_text(json.dumps(meta),encoding="utf-8")
            with self.assertRaises(ValueError):verify_package(folder,root)

    def test_outside_package_root_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):verify_package(temp,temp)


if __name__=="__main__":
    unittest.main()
