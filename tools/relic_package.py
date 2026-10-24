"""Build a reproducible single-player experimental package from a preset."""
import csv
import json
import shutil
import subprocess
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from relic_presets import ROOT, Planner, load


def build_package(preset, project_root=ROOT):
    root=Path(project_root).resolve()
    planner=Planner(load(root/"local/evidence/relic-catalog.json"),load(root/"data/relic_budgets.json"))
    with (root/"local/evidence/ShopLineupParam.csv").open(encoding="utf-8-sig") as stream:
        shops=list(csv.DictReader(stream))
    manifest=planner.experimental_combined_manifest(preset,shops)
    shell=shutil.which("pwsh")
    if not shell:
        raise ValueError("未找到PowerShell7；构建需要.NET10兼容运行时")
    folder=root/"local/packages"/(datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    (folder/"preset.json").write_text(json.dumps(preset,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest_path=folder/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    process=subprocess.run([shell,"-NoProfile","-File",str(root/"tools/build_param_patch.ps1"),
        "-ProjectRoot",str(root),"-Manifest",str(manifest_path),
        "-OutputDirectory",str(folder/"mod")],capture_output=True,text=True,encoding="utf-8",
        errors="replace",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    (folder/"build.log").write_text(process.stdout+"\n"+process.stderr,encoding="utf-8")
    if process.returncode:
        raise ValueError(f"构建未通过，查看 {folder/'build.log'}")
    # Unique test save name is intentional: never silently opens NR0000.sl2.
    save_name="NRE_"+folder.name.replace("-","_")+".sl2"
    common=f'profileVersion = "v1"\nsavefile = "{save_name}"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
    (folder/"generate.me3").write_text(common+'[[packages]]\nid = "NRE-Relic-Generation"\nsource = "./mod"\n',encoding="utf-8")
    (folder/"play.me3").write_text(common,encoding="utf-8")
    files=["generate.me3","play.me3","mod/regulation.bin","manifest.json","preset.json"]
    (folder/"package.json").write_text(json.dumps({
        "schema_version":1,"savefile":save_name,
        "sha256":{name:hashlib.sha256((folder/name).read_bytes()).hexdigest().upper() for name in files}
    },ensure_ascii=False,indent=2),encoding="utf-8")
    item_lines="\n".join(
        f"商品行 {a['shop_row_id']} → 遗物 {a['template_id']}："+
        "；".join(planner.effects[key]["Name"] for key in a["effect_ids"])+
        ("；负面："+"；".join(planner.effects[key]["Name"] for key in a.get("curse_ids",[]) if key is not None)
         if a.get("kind")=="deep" else "")
        for a in manifest["loadout_assignments"])
    vessels="\n".join(f"{v['id']} {v['name']}（槽颜色 {v['colors']}）" for v in manifest["compatible_vessels"])
    (folder/"README.txt").write_text(
        "NRE 单人隔离遗物生成包\n\n"
        "1. 完全退出游戏；配置器启动按钮将从已配置的隔离种子复制为 "+save_name+"。\n"
        "2. 使用ME3加载generate.me3，购买manifest.json列出的小壶商店绿色遗物。\n"
        "3. 装备验证后退出；使用play.me3加载同一副本，验证词条保留。\n"
        "4. play.me3不加载生成参数，避免持续改变随机掉落模板。\n\n"
        "当前限制：按难度额度分配普通/深夜词条；需适配绿色槽容器；商品须有库存；不支持多人应用。\n"
        "完整组合合法性尚未认证；这里只做原生槽位池匹配和保守冲突检查。\n\n"+
        item_lines+"\n\n可用容器（需在游戏中已获得）：\n"+vessels+"\n",
        encoding="utf-8")
    return folder
