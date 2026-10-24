"""Compose verified local relic/reward packages without running the game."""
import argparse
import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from phase1_rewards import ROOT, SOURCE, read_json
from relic_launch import sha, verify_package, launch


def inspect_inputs(relic, rewards, root):
    inputs = []
    for folder, expected in ((relic, "relic"), (rewards, "native_rewards")):
        metadata = verify_package(folder, root)
        if metadata.get("kind", "relic") != expected:
            raise ValueError("Expected package kind: " + expected)
        manifest = read_json(Path(folder) / "manifest.json")
        if manifest.get("source_sha256") != SOURCE or str(manifest.get("regulation_internal_version")) != "10350000":
            raise ValueError("Input source/version differs from reviewed original")
        if expected == "relic":
            changes = manifest.get("changes", [])
            if not changes or any(c["table"] not in ("EquipParamAntique", "ShopLineupParam") for c in changes):
                raise ValueError("Relic package has unsupported table edits")
        inputs.append(metadata)
    return inputs


def build(relic, rewards, root=ROOT, shell=None):
    root = Path(root).resolve()
    relic, rewards = Path(relic).resolve(), Path(rewards).resolve()
    metadata = inspect_inputs(relic, rewards, root)
    shell = shell or shutil.which("pwsh")
    if not shell:
        raise ValueError("PowerShell7 is required")
    folder = root / "local/packages" / ("combined_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    # Freeze inputs before composition; subsequent source changes cannot alter this package.
    (folder / "inputs").mkdir()
    for label, source, meta in zip(("relic", "rewards"), (relic, rewards), metadata):
        shutil.copyfile(source / "mod/regulation.bin", folder / "inputs" / (label + ".bin"))
        if sha(folder / "inputs" / (label + ".bin")) != meta["sha256"]["mod/regulation.bin"]:
            raise ValueError("Source changed while copying")
        shutil.copyfile(source / "manifest.json", folder / "inputs" / (label + "-manifest.json"))
        if sha(folder / "inputs" / (label + "-manifest.json")) != meta["sha256"]["manifest.json"]:
            raise ValueError("Source manifest changed while copying")
    result = subprocess.run([shell, "-NoProfile", "-File", str(root / "tools/compose_regulation.ps1"),
        "-ProjectRoot", str(root), "-RelicFile", str(folder / "inputs/relic.bin"),
        "-RewardFile", str(folder / "inputs/rewards.bin"),
        "-RelicHash", metadata[0]["sha256"]["mod/regulation.bin"],
        "-RewardHash", metadata[1]["sha256"]["mod/regulation.bin"],
        "-OutputDirectory", str(folder / "mod")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (folder / "build.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("Composition rejected: " + str(folder / "build.log"))
    (folder / "reward-mod").mkdir()
    shutil.copyfile(folder / "inputs/rewards.bin", folder / "reward-mod/regulation.bin")
    save = "NRE_" + folder.name + ".sl2"
    common = f'profileVersion = "v1"\nsavefile = "{save}"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
    (folder / "generate.me3").write_text(common + '[[packages]]\nid = "NRE-Combined-Generation"\nsource = "./mod"\n', encoding="utf-8")
    (folder / "play.me3").write_text(common + '[[packages]]\nid = "NRE-Native-Rewards"\nsource = "./reward-mod"\n', encoding="utf-8")
    (folder / "rollback.me3").write_text(common, encoding="utf-8")
    manifest = dict(schema_version=1, source_sha256=SOURCE, regulation_internal_version="10350000",
        status="BUILD_VERIFIED_GAME_PENDING", game_verified=False,
        inputs=[dict(kind=kind, package=src.name, regulation_sha256=meta["sha256"]["mod/regulation.bin"],
                     manifest_sha256=meta["sha256"]["manifest.json"])
                for kind, src, meta in zip(("relic", "native_rewards"), (relic, rewards), metadata)])
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files = ("generate.me3", "play.me3", "rollback.me3", "manifest.json", "mod/regulation.bin",
             "reward-mod/regulation.bin", "mod/build-report.json", "inputs/relic.bin", "inputs/rewards.bin",
             "inputs/relic-manifest.json", "inputs/rewards-manifest.json")
    (folder / "package.json").write_text(json.dumps(dict(schema_version=1, kind="combined",
        savefile=save, sha256={f: sha(folder / f) for f in files}), indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(
        "NRE 遗物与局内奖励整合实验包\n"
        "generate.me3：小壶遗物生成 + 局内奖励。取得配置的遗物后正常退出游戏。\n"
        "play.me3：同一独立存档，只保留局内奖励参数；生成修改已撤除。\n"
        "rollback.me3：同一独立存档，不加载参数补丁；不会删除已购遗物或存档进度。\n"
        "三种配置都通过项目启动器使用，不能在游戏运行中切换。\n"
        "具体商品与词条见 inputs/relic-manifest.json；奖励配置见 inputs/rewards-manifest.json。\n"
        "首次启动仅复制已有 NRE 隔离种子；不会自动带入两个输入包各自的游戏进度。\n"
        "组合包未做实机验证；局内叠层、去重、清理和多人仍未完成。\n", encoding="utf-8")
    verify_package(folder, root)
    (root / "local/combined-package.json").write_text(json.dumps({"path": str(folder)}, ensure_ascii=False), encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "generate", "play", "rollback", "menu"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--relic", type=Path)
    parser.add_argument("--rewards", type=Path)
    parser.add_argument("--pwsh")
    args = parser.parse_args()
    if args.action == "build":
        relic = args.relic or Path(read_json(args.root / "local/last-package.json")["path"])
        rewards = args.rewards or Path(read_json(args.root / "local/phase1/tiered_choices-package.json")["path"])
        print(build(relic, rewards, args.root, args.pwsh))
        return
    action = args.action
    if action == "menu":
        print("1：生成遗物 + 局内奖励\n2：只加载局内奖励（同一存档）\n3：无补丁对照（保留存档）\n其他输入：退出")
        action = {"1": "generate", "2": "play", "3": "rollback"}.get(input("请选择：").strip())
        if action is None:
            return
    folder = Path(read_json(args.root / "local/combined-package.json")["path"])
    if verify_package(folder, args.root).get("kind") != "combined":
        raise ValueError("Expected combined package")
    print(launch(folder, action == "generate", args.root, rollback=action == "rollback"))


if __name__ == "__main__":
    main()
