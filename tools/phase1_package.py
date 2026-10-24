"""Build/launch the audited native reward experiments in isolated offline saves."""
import argparse
import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from phase1_rewards import ROOT, MODES, read_json, load_tables, compile_manifest
from relic_launch import sha, verify_package, launch


def build(root, mode, shell, config=None):
    root = Path(root).resolve()
    config = config if config is not None else read_json(root / "data/phase1_native_buffs.json")
    manifest = compile_manifest(config, load_tables(root), mode)
    name = "phase1_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    folder = root / "local/packages" / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    builder = "build_reward_pools.ps1" if manifest["schema_version"]==2 else "build_param_patch.ps1"
    result = subprocess.run([shell, "-NoProfile", "-File", str(root / "tools" / builder),
                             "-ProjectRoot", str(root), "-Manifest", str(folder / "manifest.json"),
                             "-OutputDirectory", str(folder / "mod")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (folder / "build.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("Build rejected: " + str(folder / "build.log"))
    save = "NRE_" + name + ".sl2"
    common = f'profileVersion = "v1"\nsavefile = "{save}"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
    (folder / "generate.me3").write_text(common + '[[packages]]\nid = "NRE-Native-Rewards"\nsource = "./mod"\n', encoding="utf-8")
    (folder / "play.me3").write_text(common, encoding="utf-8")
    files = ("generate.me3", "play.me3", "mod/regulation.bin", "manifest.json", "config.json")
    (folder / "package.json").write_text(json.dumps(dict(schema_version=1, kind="native_rewards",
        savefile=save, sha256={f: sha(folder / f) for f in files}), indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(
        "NRE 局内原生奖励实验包\n模式：" + mode + "\n"
        "运行带补丁配置，进入远征观察堡垒首领潜在力量奖励。不会自动领取。\n"
        "weighted：只提高六项数值奖励的池内权重，其他条目仍保留。\n"
        "three_choices_probe：额外将堡垒6000050/51两条武器奖励路径改到潜在力量池。\n"
        "distinct_choices：三个奖励路径分别指向生存/攻击/防御原生子池，候选物品与效果集合互不重叠。\n"
        "tiered_choices：使用项目专用两层池，按普通/稀有权重选择原生效果；不改共享池。\n"
        "三选一实际显示、重复选项、叠层、复活、远征清理仍待实机；本包未实现机制去重。\n"
        "play.me3是无补丁回滚对照；不要像遗物生成包一样将它误当日常运行配置。\n"
        "退出游戏后才能切换；沿用同一隔离副本，不修改正式存档。\n",
        encoding="utf-8")
    verify_package(folder, root)
    locator = root / "local/phase1" / (mode + "-package.json")
    locator.parent.mkdir(parents=True, exist_ok=True)
    locator.write_text(json.dumps({"path": str(folder)}, ensure_ascii=False), encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "launch", "rollback"))
    parser.add_argument("--mode", choices=MODES, default="weighted")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pwsh", default=shutil.which("pwsh"))
    parser.add_argument("--config", type=Path, help="Optional saved native reward configuration")
    args = parser.parse_args()
    if args.action == "build":
        if not args.pwsh:
            raise ValueError("PowerShell7 is required")
        print(build(args.root, args.mode, args.pwsh, read_json(args.config) if args.config else None))
    else:
        folder = Path(read_json(args.root / "local/phase1" / (args.mode + "-package.json"))["path"])
        metadata = verify_package(folder, args.root)
        if metadata.get("kind") != "native_rewards":
            raise ValueError("Not a native reward package")
        print(launch(folder, args.action == "launch", args.root))


if __name__ == "__main__":
    main()
