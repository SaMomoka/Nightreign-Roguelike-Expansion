"""Local integration checks against the user's pinned regulation; no game launch."""
import argparse
import copy
import json
import subprocess
import tempfile
from pathlib import Path
from phase1_rewards import ROOT, read_json
from relic_launch import verify_package, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pwsh", required=True)
    args = parser.parse_args()
    checks = []
    for mode, expected in (("weighted", 6), ("three_choices_probe", 13), ("distinct_choices",14)):
        folder = Path(read_json(ROOT / "local/phase1" / (mode + "-package.json"))["path"])
        verify_package(folder)
        report = read_json(folder / "mod/build-report.json")
        assert len(report["changes"]) == expected and report["other_resources_unchanged"]
        checks.append(dict(case=mode, status="PASS", changed_cells=expected,
                           output_sha256=sha(folder / "mod/regulation.bin")))
    base = read_json(ROOT / "local/phase1/weighted/manifest.json")
    with tempfile.TemporaryDirectory(prefix="rejection_", dir=str(ROOT / "local/phase1")) as temporary:
        work = Path(temporary)
        for case in ("wrong_ordinal", "wrong_guard", "overflow_weight", "missing_guard"):
            plan = copy.deepcopy(base)
            change = plan["changes"][0]
            if case == "wrong_ordinal": change["row_ordinal"] = 0
            elif case == "wrong_guard": change["guard"]["itemId"] = 999
            elif case == "overflow_weight": change["after"] = 65536
            else: del change["guard"]
            path = work / (case + ".json")
            path.write_text(json.dumps(plan), encoding="utf-8")
            out = work / (case + "_out")
            process = subprocess.run([args.pwsh, "-NoProfile", "-File", str(ROOT / "tools/build_param_patch.ps1"),
                "-Manifest", str(path), "-OutputDirectory", str(out)],
                capture_output=True, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            assert process.returncode != 0 and not (out / "regulation.bin").exists(), case
            checks.append(dict(case=case, status="REJECTED_AS_EXPECTED"))
    result = dict(status="PASS", game_verified=False, checks=checks)
    (ROOT / "tests/ingame/PHASE1-build-checks.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
