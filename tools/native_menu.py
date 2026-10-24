"""Package a native ESD/FMG merchant menu. No external gameplay UI or live hook."""
import argparse
import json
import shutil
import struct
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from phase1_rewards import ROOT, SOURCE, read_json
from relic_launch import sha, verify_package, launch

ARCHIVE_HASH = "BB295CFC9F6C8ADF8D7DA261A5FC98095BDF03044DDAC9E99D69621496BF2B2C"
ASSETS = ("script/talk/m10_00_00_00.talkesdbnd.dcx",
          "msg/zhocn/menu_dlc01.msgbnd.dcx", "msg/engus/menu_dlc01.msgbnd.dcx")


def specification(manifest):
    if manifest.get("source_sha256") != SOURCE:
        raise ValueError("Unreviewed source")
    assignments = manifest.get("loadout_assignments", [])
    if not 1 <= len(assignments) <= 6:
        raise ValueError("Expected one to six existing relic assignments")
    presets, rows = [], set()
    for index, assignment in enumerate(assignments):
        row = assignment["shop_row_id"]
        if type(row) is not int or not 10000 <= row <= 10999 or row in rows:
            raise ValueError("Invalid or repeated shop row")
        rows.add(row)
        links = [c for c in manifest["changes"] if c["table"] == "ShopLineupParam"
                 and c["row_id"] == row and c["field"] == "equipId"]
        if len(links) != 1 or links[0]["after"] != assignment["template_id"]:
            raise ValueError("Menu selection is not linked to the selected relic")
        count = len(assignment["effect_ids"])
        if not 1 <= count <= 3:
            raise ValueError("Invalid positive effect count")
        deep = assignment.get("kind") == "deep"
        presets.append(dict(shop_row_id=row, template_id=assignment["template_id"],
            effect_ids=assignment["effect_ids"], curse_ids=assignment.get("curse_ids", []),
            labels=dict(zhocn=f"{'深夜' if deep else '普通'}遗物 {index+1}（{count}词条，详情见商店）",
                        engus=f"{'Deep' if deep else 'Normal'} relic {index+1} ({count} effects; shop details)")))
    return dict(schema_version=1, presets=presets)


def decode_integer(hex_value):
    value = bytes.fromhex(hex_value)
    if len(value) == 6 and value[0] == 0x82 and value[-1] == 0xA1:
        return struct.unpack("<i", value[1:5])[0]
    raise ValueError("Expected reviewed integer expression")


def audit_graph(report, spec):
    """Audit emitted ESD graph, not a simulation of menu/game behavior."""
    rows = report["graph"]
    graph = {r["state"]: r for r in rows}
    if len(graph) != len(rows) or set(graph) != {1, *range(100000, 100008 + len(spec["presets"]))}:
        raise ValueError("Unexpected allocated states")
    for row in rows:
        if any(c["target"] not in graph and c["target"] not in (2, 10) for c in row["conditions"]):
            raise ValueError("Dangling menu state")
    # Cycles are permitted only through a retained native modal wait.
    waiting = {100001, 100006, 100003, *range(100008, 100008 + len(spec["presets"]))}
    for node in waiting:
        conditions = graph[node]["conditions"]
        if not conditions or any(c["evaluator"] == "41A1" for c in conditions):
            raise ValueError("Modal wait replaced with unconditional transition")
    seen, active = set(), set()
    def visit(node):
        if node in waiting or node in (2, 10):
            return
        if node not in graph:
            raise ValueError("Unknown menu state")
        if node in active:
            raise ValueError("Menu cycle without modal wait")
        if node in seen:
            return
        active.add(node)
        for condition in graph[node]["conditions"]:
            visit(condition["target"])
        active.remove(node)
        seen.add(node)
    for node in graph:
        visit(node)
    expected_shops = {100003: (10000, 10999)}
    expected_shops.update({100008 + i: (p["shop_row_id"], p["shop_row_id"])
                           for i, p in enumerate(spec["presets"])})
    actual_shops = {}
    for node, row in graph.items():
        for command in row["commands"]:
            if (command["bank"], command["id"]) == (1, 155):
                actual_shops[node] = tuple(map(decode_integer, command["args"]))
    if actual_shops != expected_shops:
        raise ValueError("Unexpected shop range or original shop lost")
    if len(graph[100000]["commands"]) != 3 or len(graph[100005]["commands"]) != len(spec["presets"]) + 1:
        raise ValueError("Missing menu choice/back button")
    return dict(state_targets_checked=True, no_cycles_without_modal_wait=True,
                original_shop_preserved=True, preset_shop_ranges_checked=True)


def build(source, root=ROOT, shell=None):
    root, source = Path(root).resolve(), Path(source).resolve()
    metadata = verify_package(source, root)
    if metadata.get("kind") != "combined":
        raise ValueError("Build the combined package first")
    spec = specification(read_json(source / "inputs/relic-manifest.json"))
    shell = shell or shutil.which("pwsh")
    if not shell:
        raise ValueError("PowerShell7 is required")
    folder = root / "local/packages" / ("native_menu_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    for relative, expected in metadata["sha256"].items():
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
        if sha(target) != expected:
            raise ValueError("Combined source changed while copying")
    (folder / "menu-spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run([shell, "-NoProfile", "-File", str(root / "tools/build_native_menu.ps1"),
        "-ProjectRoot", str(root), "-Spec", str(folder / "menu-spec.json"),
        "-OutputDirectory", str(folder / "ui-build")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (folder / "ui-build.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("Native menu build rejected: " + str(folder / "ui-build.log"))
    report = read_json(folder / "ui-build/native-menu-report.json")
    report["graph_audit"] = audit_graph(report, spec)
    for asset in ASSETS:
        target = folder / "mod" / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / "ui-build" / asset, target)
    (folder / "native-menu-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = read_json(folder / "manifest.json")
    manifest.update(native_menu=True, archive_header_sha256=ARCHIVE_HASH, combined_source=source.name)
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    save = "NRE_" + folder.name + ".sl2"
    for name in ("generate.me3", "play.me3", "rollback.me3"):
        profile = (folder / name).read_text(encoding="utf-8").replace(metadata["savefile"], save)
        if name == "generate.me3":
            profile = profile.replace("NRE-Combined-Generation", "NRE-Native-Menu")
        (folder / name).write_text(profile, encoding="utf-8")
    files = set(metadata["sha256"]) | {"menu-spec.json", "native-menu-report.json"} | {"mod/" + p for p in ASSETS}
    new_meta = dict(schema_version=1, kind="native_menu", savefile=save,
                    sha256={p: sha(folder / p) for p in sorted(files)})
    (folder / "package.json").write_text(json.dumps(new_meta, indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(
        "NRE 原生菜单实验\n进入隔离副本，与小壶商人交互：原商店 / NRE遗物选择 / 离开。\n"
        "NRE遗物选择列出本包预设，选中后使用原生商店购买，取消或返回可回上一级。\n"
        "按钮、菜单、购买均由游戏 ESD/FMG/商店资源处理，不需打开外部配置窗口。\n"
        "这版仅选择构建时已有的预设；不能任意拼接词条、改难度额度或动态改变奖励权重。\n"
        "保留原商品价格、库存和解锁条件，不自动发放或扣款。只包含简中/英文新增文本。\n"
        "generate.me3加载此菜单及整合参数；play.me3仅奖励、撤除遗物生成及新增菜单；rollback.me3无补丁。\n"
        "菜单游戏内显示/输入/返回/购买仍待实测。用户要求暂缓实机，本轮未启动。\n",
        encoding="utf-8")
    verify_package(folder, root)
    (root / "local/native-menu-package.json").write_text(json.dumps({"path": str(folder)}, ensure_ascii=False), encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "launch", "play", "rollback"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--pwsh")
    args = parser.parse_args()
    if args.action == "build":
        source = args.source or Path(read_json(args.root / "local/combined-package.json")["path"])
        print(build(source, args.root, args.pwsh))
    else:
        folder = Path(read_json(args.root / "local/native-menu-package.json")["path"])
        if verify_package(folder, args.root).get("kind") != "native_menu":
            raise ValueError("Expected native menu package")
        print(launch(folder, args.action == "launch", args.root, rollback=args.action == "rollback"))


if __name__ == "__main__":
    main()
