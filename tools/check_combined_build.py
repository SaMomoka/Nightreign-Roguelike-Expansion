"""Real regulation integration checks; never starts a game or touches a save."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path
from combined_package import build
from phase1_rewards import ROOT, read_json
from relic_launch import sha


def run(root, shell):
    relic = Path(read_json(root / "local/last-package.json")["path"])
    rewards = Path(read_json(root / "local/phase1/tiered_choices-package.json")["path"])
    folder = build(relic, rewards, root, shell)
    report = read_json(folder / "mod/build-report.json")
    assert report["all_resources_roundtrip_verified"] and report["resource_count"] == 252
    assert report["relic_resources"] == 2 and report["reward_resources"] == 2
    assert sum(r["origin"] == "original" for r in report["resources"]) == 248
    assert sha(folder / "reward-mod/regulation.bin") == sha(rewards / "mod/regulation.bin")
    left, right = relic / "mod/regulation.bin", rewards / "mod/regulation.bin"
    cases = (
        ("conflict", left, left, sha(left), "Conflicting resource"),
        ("swapped", right, left, sha(right), "Unexpected"),
        ("input_changed", left, right, "0" * 64, "Input package changed"),
        ("missing_relic_changes", root / "local/inputs/regulation.bin", right,
         sha(root / "local/inputs/regulation.bin"), "Expected relic and reward changes"),
        ("existing_output", left, right, sha(left), "Output already exists"),
        ("outside_output", left, right, sha(left), "Output outside project/local"),
    )
    results = []
    for label, a, b, digest, expected in cases:
        target = root / "local/composition-checks" / (label + "_" + uuid.uuid4().hex[:8])
        if label == "existing_output":
            target = folder / "mod"
        if label == "outside_output":
            target = root / ("must_not_create_" + uuid.uuid4().hex[:8])
        process = subprocess.run([shell, "-NoProfile", "-File", str(root / "tools/compose_regulation.ps1"),
            "-ProjectRoot", str(root), "-RelicFile", str(a), "-RewardFile", str(b),
            "-RelicHash", digest, "-RewardHash", sha(b), "-OutputDirectory", str(target)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode == 0 or expected not in process.stdout + process.stderr:
            raise AssertionError(label + ": " + process.stdout + process.stderr)
        if label != "existing_output" and target.exists():
            raise AssertionError("Rejected build created output: " + label)
        results.append({"case": label, "status": "PASS"})
    result = dict(status="PASS", package=folder.name, resource_count=252, original_resources=248,
                  relic_resources=2, reward_resources=2, negative_cases=results,
                  game_launched=False, game_verified=False)
    path = root / "tests/ingame/PHASE1-combined-build.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pwsh", required=True)
    args = parser.parse_args()
    run(args.root, args.pwsh)
