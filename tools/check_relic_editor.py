"""Validate the actual generated editor and reject corrupted crafting plans."""
import argparse
import copy
import json
import subprocess
import uuid
from pathlib import Path
from relic_editor import ROOT, load, audit_plan
from relic_launch import verify_package


def run(root,shell):
    folder=Path(load(root/"local/relic-editor-package.json")["path"])
    verify_package(folder,root)
    plan=load(folder/"editor-plan.json")
    audit_plan(plan)
    checks=[]
    for case in ("incomplete_purchase","deep_curse_removed","wrong_product","wrong_currency","duplicate_effect","wrong_entry_count"):
        data=copy.deepcopy(plan)
        editor=next(p for p in data["pages"] if "editor" in p and not any(p["selection"]))
        if case=="incomplete_purchase":editor["entries"][3]["target"]=data["purchases"][0]["state"]
        if case=="deep_curse_removed":next(p for p in data["products"] if p["kind"]=="deep")["curses"]=[None]*3
        if case=="wrong_product":data["purchases"][0]["shop_id"]=data["products"][-1]["shop_id"]
        if case=="wrong_currency":data["currency_cost_type"]=0
        if case=="duplicate_effect":editor["selection"]=[7000000,7000000,0]
        if case=="wrong_entry_count":editor["entries"].pop()
        try:audit_plan(data)
        except ValueError:checks.append(dict(case=case,status="PASS"))
        else:raise AssertionError(case+" accepted")
    for case,expected in (("price_not_one","Unsupported editor plan"),("random_effect_pool","Non-deterministic effect pool"),
                          ("removed_required_curse","Curse removed from required slot"),("duplicate_product_id","Invalid product allocation")):
        data=copy.deepcopy(plan)
        if case=="price_not_one":data["price"]=2
        if case=="random_effect_pool":data["products"][0]["relic_overrides"]["attachEffectTableId_1"]=100
        if case=="removed_required_curse":
            item=next(p for p in data["products"] if p["kind"]=="deep")
            item["curses"][0]=None;item["relic_overrides"]["attachEffectTableId_curse1"]=-1
        if case=="duplicate_product_id":data["products"][1]["relic_id"]=data["products"][0]["relic_id"]
        path=folder/(case+".json")
        path.write_text(json.dumps(data),encoding="utf-8")
        out=root/"local/relic-editor-checks"/(case+"_"+uuid.uuid4().hex[:6])
        result=subprocess.run([shell,"-NoProfile","-File",str(root/"tools/build_relic_editor.ps1"),
            "-ProjectRoot",str(root),"-Plan",str(path),"-RewardBase",str(folder/"reward-base.bin"),"-OutputDirectory",str(out)],
            capture_output=True,text=True,encoding="utf-8",errors="replace",
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if not result.returncode or expected not in result.stdout+result.stderr:
            raise AssertionError(case+": "+result.stdout+result.stderr)
        if out.exists():raise AssertionError("Rejected product generated output")
        checks.append(dict(case=case,status="PASS"))
    report=load(folder/"mod/editor-report.json")
    report.update(package=folder.name,status="PASS_BUILD_GAME_PENDING",negative_checks=checks,
                  normal_products=sum(p["kind"]=="normal" for p in plan["products"]),
                  deep_products=sum(p["kind"]=="deep" for p in plan["products"]),
                  game_launched_this_check=False)
    (root/"tests/ingame/RELIC-EDITOR-build.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--pwsh",required=True)
    args=parser.parse_args();run(args.root,args.pwsh)
