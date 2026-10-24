"""Integration tests against generated native ESD/FMG files; no game launch."""
import argparse
import copy
import json
import subprocess
import uuid
from pathlib import Path
from native_menu import ROOT, ASSETS, build, audit_graph, specification, read_json
from relic_launch import verify_package, sha


def run(root, shell):
    source = Path(read_json(root / "local/combined-package.json")["path"])
    folder = build(source, root, shell)
    metadata = verify_package(folder, root)
    report = read_json(folder / "native-menu-report.json")
    spec = read_json(folder / "menu-spec.json")
    checks = []
    for case in ("unguarded_cycle", "lost_wait", "wrong_shop", "missing_back", "dangling", "duplicate_state"):
        altered = copy.deepcopy(report)
        graph = {r["state"]: r for r in altered["graph"]}
        if case == "unguarded_cycle": graph[100000]["conditions"][0]["target"] = 1
        if case == "lost_wait": graph[100001]["conditions"][0]["evaluator"] = "41A1"
        if case == "wrong_shop": graph[100008]["commands"][0]["args"][0] = "8210270000A1"
        if case == "missing_back": graph[100005]["commands"].pop()
        if case == "dangling": graph[100008]["conditions"][0]["target"] = 999999
        if case == "duplicate_state": altered["graph"].append(copy.deepcopy(altered["graph"][0]))
        try:
            audit_graph(altered, spec)
        except ValueError:
            checks.append(dict(case=case, status="PASS"))
        else:
            raise AssertionError("Graph corruption accepted: " + case)
    for case in ("outside_shop", "duplicate_shop", "empty_label", "too_many_presets"):
        altered = copy.deepcopy(spec)
        if case == "outside_shop": altered["presets"][0]["shop_row_id"] = 9999
        if case == "duplicate_shop": altered["presets"].append(copy.deepcopy(altered["presets"][0]))
        if case == "empty_label": altered["presets"][0]["labels"]["zhocn"] = ""
        if case == "too_many_presets": altered["presets"] = altered["presets"] * 7
        path = folder / (case + ".json")
        path.write_text(json.dumps(altered), encoding="utf-8")
        output = root / "local/native-menu/checks" / (case + "_" + uuid.uuid4().hex[:6])
        result = subprocess.run([shell, "-NoProfile", "-File", str(root / "tools/build_native_menu.ps1"),
            "-ProjectRoot", str(root), "-Spec", str(path), "-OutputDirectory", str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0 or output.exists() or "Invalid" not in result.stderr:
            raise AssertionError(case + ": " + result.stdout + result.stderr)
        checks.append(dict(case=case, status="PASS"))
    assert sha(folder / "mod/regulation.bin") == sha(source / "mod/regulation.bin")
    assert sha(folder / "reward-mod/regulation.bin") == sha(source / "reward-mod/regulation.bin")
    result = dict(status="PASS", package=folder.name, game_launched=False, game_verified=False,
                  new_states=report["new_states"], modified_original_states=report["modified_original_states"],
                  added_texts=report["added_texts"], menu_presets=len(spec["presets"]),
                  graph_audit=report["graph_audit"], original_esd_restoration_verified=True,
                  binder_roundtrip_verified=True, regulation_unchanged_from_combined=True,
                  negative_cases=checks, resources={p: metadata["sha256"]["mod/" + p] for p in ASSETS})
    (root / "tests/ingame/NATIVE-MENU-build.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pwsh", required=True)
    args = parser.parse_args()
    run(args.root, args.pwsh)
