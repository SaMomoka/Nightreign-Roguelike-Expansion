"""Integration rejection tests using local pinned regulation, without launching the game."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from phase1_rewards import ROOT, read_json
from relic_launch import verify_package


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pwsh",required=True)
    args=parser.parse_args()
    folder=Path(read_json(ROOT/"local/phase1/tiered_choices-package.json")["path"])
    verify_package(folder)
    plan=read_json(folder/"manifest.json")
    report=read_json(folder/"mod/build-report.json")
    assert report["new_rows"]==32 and report["private_pool_count"]==9
    assert len(report["changes"])==8 and report["original_item_table_rows_unchanged"]
    checks=[dict(case="full_roundtrip",status="PASS",new_rows=32,route_changes=8)]
    with tempfile.TemporaryDirectory(prefix="tier_rejections_",dir=str(ROOT/"local/phase1")) as temp:
        directory=Path(temp)
        for case in ("cycle","missing_target","empty_root","collision","wrong_template",
                     "overflow","arbitrary_field","wrong_route"):
            bad=copy.deepcopy(plan)
            first=bad["additions"][0]
            if case=="cycle":first["overrides"]["itemId"]=first["row_id"]
            elif case=="missing_target":first["overrides"]["itemId"]=1900100999
            elif case=="empty_root":
                for a in bad["additions"]:
                    if a["row_id"]==first["row_id"]:a["overrides"]["chanceWeight"]=0
            elif case=="collision":first["row_id"]=1200600
            elif case=="wrong_template":first["source_ordinal"]=0
            elif case=="overflow":first["overrides"]["chanceWeight"]=65536
            elif case=="arbitrary_field":first["overrides"]["unknown_7"]=999
            elif case=="wrong_route":bad["changes"][0]["after"]+=1
            path=directory/(case+".json")
            path.write_text(json.dumps(bad),encoding="utf-8")
            output=directory/(case+"_out")
            process=subprocess.run([args.pwsh,"-NoProfile","-File",str(ROOT/"tools/build_reward_pools.ps1"),
                "-Manifest",str(path),"-OutputDirectory",str(output)],
                capture_output=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            assert process.returncode!=0 and not (output/"regulation.bin").exists(),case
            checks.append(dict(case=case,status="REJECTED_AS_EXPECTED"))
    (ROOT/"tests/ingame/PHASE1-tiered-build.json").write_text(
        json.dumps(dict(status="PASS",game_verified=False,checks=checks),indent=2),encoding="utf-8")
    print(json.dumps(checks,indent=2))


if __name__=="__main__":
    main()
