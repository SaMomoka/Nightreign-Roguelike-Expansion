"""Build and launch a native full-catalog editor with a headless local adapter."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from relic_presets import ROOT,load
from relic_launch import verify_package,sha,launch
from full_relic_menu import compile_menu
from native_menu import ASSETS,ARCHIVE_HASH
from phase1_rewards import SOURCE
from relic_filters import bind_filters, color_products, COLORS

RUNTIME_TOOLS=("relic_runtime.py","relic_selection.py","full_relic_menu.py",
               "probe_relic_params.py","probe_relic_work_values.py","relic_filters.py")


def build(root=ROOT,shell=None):
    root=Path(root)
    source=Path(load(root/"local/relic-editor-package.json")["path"])
    old=verify_package(source,root)
    if old["kind"]!="relic_editor":raise ValueError("Expected verified static editor base")
    catalog=load(root/"local/evidence/relic-full-catalog.json")
    if catalog["source_sha256"]!=SOURCE:raise ValueError("Unsupported catalog")
    native=load(root/'local/evidence/relic-filters.json')
    bind_filters(catalog,native)
    # Keep the exact data used by the runtime in the hashed package. Large
    # source-reference lists remain in the ignored research evidence folder.
    compact=dict(schema_version=1,source_sha256=SOURCE,entries=[
        {k:v for k,v in e.items() if k not in ("native_links","references","reference_labels","info")}
        for e in catalog["entries"]])
    aliases=[]
    selectable=sorted((e for e in compact['entries'] if e['selectable_modes']),key=lambda e:e['effect_id'])
    for index,e in enumerate(selectable):
        e['duplicate_pools']=[e['deterministic_pool']]
        for occurrence in (1,2):
            alias_id=1800000000+index*2+occurrence-1
            aliases.append(dict(source_effect=e['effect_id'],source_pool=e['deterministic_pool'],
                effect_id=alias_id,pool_id=alias_id,occurrence=occurrence))
            e['duplicate_pools'].append(alias_id)
    plan=compile_menu(compact)
    plan['duplicate_aliases']=aliases

    by_id={e["effect_id"]:e for e in compact["entries"]}
    plan["initial_products"]=[]
    for product in color_products(native):
        editor=product['editor']
        positives=(7000000,7000100,7000200) if editor<2 else (6001400,6003000,6003100)
        negatives=(None,None,None) if editor<2 else (6830000,None,None)
        fields={}
        for slot,(p,n) in enumerate(zip(positives,negatives),1):
            fields[f"attachEffectTableId_{slot}"]=by_id[p]["deterministic_pool"]
            fields[f"attachEffectTableId_curse{slot}"]=-1 if n is None else by_id[n]["deterministic_pool"]
        product['fields']=fields
        plan["initial_products"].append(product)
    folder=root/"local/packages"/("full_relic_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    for relative in ["mod/regulation.bin"]+["mod/"+p for p in ASSETS]:
        dest=folder/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/relative,dest)
    for name,data in (("full-menu-plan.json",plan),("runtime-catalog.json",compact)):
        (folder/name).write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    shell=shell or shutil.which("pwsh")
    if not shell:raise ValueError("PowerShell 7 required")
    result=subprocess.run([shell,"-NoProfile","-File",str(root/"tools/build_full_relic_menu.ps1"),
        "-ProjectRoot",str(root),"-Package",str(folder)],capture_output=True,text=True,
        encoding="utf-8",errors="replace",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    (folder/"build.log").write_text(result.stdout+"\n"+result.stderr,encoding="utf-8")
    if result.returncode:raise ValueError("Full menu build failed: "+str(folder/"build.log"))
    save="NRE_"+folder.name+".sl2"
    profile=f'profileVersion = "v1"\nsavefile = "{save}"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n[[packages]]\nid = "NRE-Full-Relic-Editor"\nsource = "./mod"\n'
    for name in ("generate.me3","play.me3"):(folder/name).write_text(profile,encoding="utf-8")
    manifest=dict(schema_version=1,source_sha256=SOURCE,archive_header_sha256=ARCHIVE_HASH,
        regulation_internal_version="10350000",game_verified=False,
        source_package=source.name,workbook_sha256=catalog["reference"]["sha256"],
        limitations=["Full runtime crafting and persistence require in-game verification.",
                     "Headless adapter updates only eight owned color-specific mod parameter rows and one owned work-value response.",
                     "Duplicate slots use custom effect IDs and require this package to remain loaded; preservation and stacking need game testing.",
                     "Requires this package and its local adapter; no multiplayer verification."])
    (folder/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    files=["generate.me3","play.me3","manifest.json","full-menu-plan.json","runtime-catalog.json",
           "runtime-layout.json","full-build-report.json","mod/regulation.bin"]+["mod/"+p for p in ASSETS]+[f"mod/msg/{lang}/item_dlc01.msgbnd.dcx" for lang in ('zhocn','engus')]
    metadata=dict(schema_version=1,kind="full_relic_editor",savefile=save,
        sha256={name:sha(folder/name) for name in files},
        tool_hashes={name:sha(root/"tools"/name) for name in RUNTIME_TOOLS})
    (folder/"package.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    verify_package(folder,root)
    (root/"local/full-relic-package.json").write_text(json.dumps(dict(path=str(folder)),ensure_ascii=False),encoding="utf-8")
    return folder


def start(root=ROOT):
    root=Path(root)
    folder=Path(load(root/"local/full-relic-package.json")["path"])
    if verify_package(folder,root)["kind"]!="full_relic_editor":raise ValueError("Wrong package")
    started=time.time()
    game=launch(folder,True,root)
    with (folder/"runtime.log").open("ab") as log:
        helper=subprocess.Popen([sys.executable,str(root/"tools/relic_runtime.py"),
            "--root",str(root),"--package",str(folder),"--launched-after",str(started)],
            stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return dict(game=game,helper_pid=helper.pid)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("build","launch"))
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--pwsh")
    args=parser.parse_args()
    print(build(args.root,args.pwsh) if args.action=="build" else start(args.root))
