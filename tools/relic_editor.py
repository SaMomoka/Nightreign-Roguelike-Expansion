"""Compile in-game relic editors to native ESD, shops and deterministic relic rows."""
import argparse
import csv
import itertools
import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from relic_presets import Planner, load, ROOT, CHARACTERS
from relic_launch import sha, verify_package, launch
from phase1_rewards import SOURCE
from native_menu import ARCHIVE_HASH, ASSETS

NORMAL = (7000000, 7000100, 7000200, 7000300, 7000400, 7000500)
DEEP_FIRST = (6001400, 6001500, 6001600)
DEEP_FREE = (6003000,6003100,6003200,6003300,6003400,6003500,6003600)
CURSE = 6830000
RELIC_BASE = 9000000
SHOP_BASE = 1900200000
TEXT_BASE = 1900300000
STATE_BASE = 200000
LABELS = {
    7000000:("生命力 +1","Vigor +1"),7000100:("集中力 +1","Mind +1"),
    7000200:("耐力 +1","Endurance +1"),7000300:("力气 +1","Strength +1"),
    7000400:("灵巧 +1","Dexterity +1"),7000500:("智力 +1","Intelligence +1"),
    6001400:("物理攻击 +3；力气、智力降低","Physical attack +3; STR/INT down"),
    6001500:("魔力攻击 +3；力气、智力降低","Magic attack +3; STR/INT down"),
    6001600:("火攻击 +3；力气、智力降低","Fire attack +3; STR/INT down"),
    6003000:("抗毒性 +1","Poison resistance +1"),6003100:("抗出血 +1","Blood loss resistance +1"),
    6003200:("抗催眠 +1","Sleep resistance +1"),6003300:("抗咒死 +1","Death blight resistance +1"),
    6003400:("抗腐败 +1","Rot resistance +1"),6003500:("抗冻伤 +1","Frost resistance +1"),
    6003600:("抗发狂 +1","Madness resistance +1"),
}


def drafts(options):
    return [v for v in itertools.product(*[(0,) + tuple(slot) for slot in options])
            if len([x for x in v if x]) == len(set(x for x in v if x))]


def compile_plan(catalog, budgets, shops, antiques):
    planner = Planner(catalog, budgets)
    if catalog["regulation_sha256"] != SOURCE:
        raise ValueError("Unreviewed relic source")
    for effect in set(NORMAL+DEEP_FIRST+DEEP_FREE+(CURSE,)):
        if effect not in planner.effects or effect not in planner.fixed_pools:
            raise ValueError("Missing verified deterministic effect pool")
        if any(planner.effects[effect].get("allow"+c) != "1" for c in CHARACTERS):
            raise ValueError("Candidate requires character-specific menu filtering")
    if not set(NORMAL) <= planner.normal or not set(DEEP_FIRST) <= planner.curse_required or not set(DEEP_FREE) <= planner.curse_free:
        raise ValueError("Candidate native pool classification changed")
    if CURSE not in planner.curses:
        raise ValueError("Missing required curse")
    shop_index = {int(r["ID"]): r for r in shops}
    antique_index = {int(r["ID"]): r for r in antiques}
    products, product_index = [], {}
    for kind, options in (("normal",(NORMAL,)*3), ("deep",(DEEP_FIRST,DEEP_FREE,DEEP_FREE))):
        for values in drafts(options):
            if not all(values):
                continue
            canonical = tuple(sorted(values, key=lambda x:(int(planner.effects[x]["overrideBaseEffectId"]),x)))
            key = (kind,canonical)
            if key in product_index:
                continue
            preset = planner.new("Ironeye", "normal" if kind=="normal" else "deep", None if kind=="normal" else 5)
            if kind == "normal":
                preset["normal_effects"] = list(canonical)
                verdict = planner.validate(preset)
                if not verdict["valid_draft"]:
                    raise ValueError("Curated combination invalid: "+str(verdict["errors"]))
                assignment = planner.native_slot_assignment(canonical,3)
                template = assignment["template_id"]
                curses = (None,None,None)
            else:
                preset["deep_bundles"] = [dict(effect_id=x,curse_id=CURSE if x in DEEP_FIRST else None) for x in canonical]
                evidence = planner.experimental_deep_manifest(preset,3,shop_index[10036])
                template = evidence["carrier_id"]
                curses = tuple(b["curse_id"] for b in evidence["ordered_bundles"])
            index = len(products)
            relic_id, shop_id = RELIC_BASE+index, SHOP_BASE+index
            if relic_id in antique_index or shop_id in shop_index:
                raise ValueError("NRE allocation collision")
            fields = {}
            for slot, (positive, negative) in enumerate(zip(canonical,curses),1):
                fields[f"attachEffectTableId_{slot}"] = planner.fixed_pools[positive]
                fields[f"attachEffectTableId_curse{slot}"] = -1 if negative is None else planner.fixed_pools[negative]
            guard_fields = ["isDeepRelic","relicColor"] + list(fields)
            products.append(dict(kind=kind, effects=list(canonical), curses=list(curses),
                relic_id=relic_id, shop_id=shop_id, template_id=template,
                template_guard={f:int(antique_index[template][f]) for f in guard_fields},
                relic_overrides=fields))
            product_index[key] = shop_id
    texts, text_ids, pages, purchases = [], {}, {}, {}
    def text(zh, en):
        key=(zh,en)
        if key not in text_ids:
            text_ids[key] = TEXT_BASE+len(texts)
            texts.append(dict(id=text_ids[key],zhocn=zh,engus=en))
        return text_ids[key]
    def entry(zh,en,target):
        return dict(text_id=text(zh,en),target=target)
    pages["root"] = dict(back="exit", entries=[
        entry("原商店","Original shop","original_shop"),
        entry("NRE 遗物制作","NRE relic crafting","select"),
        entry("离开","Leave","exit")])
    pages["select"] = dict(back="root",entries=[])
    for number, kind in enumerate(("normal","normal","deep","deep")):
        owner = "editor"+str(number)
        index = number%2+1
        options = (NORMAL,)*3 if kind=="normal" else (DEEP_FIRST,DEEP_FREE,DEEP_FREE)
        values_list = drafts(options)
        def name(values):
            return owner+"_"+ "_".join(map(str,values))
        pages["select"]["entries"].append(entry(
            ("普通" if kind=="normal" else "深夜")+f"遗物 {index}",
            ("Normal" if kind=="normal" else "Deep")+f" relic {index}",name((0,0,0))))
        for values in values_list:
            page = name(values)
            choices = []
            for slot in range(3):
                current = LABELS[values[slot]] if values[slot] else ("未选择","Not selected")
                picker = page+"_slot"+str(slot)
                choices.append(entry(f"词条 {slot+1}：{current[0]}",f"Effect {slot+1}: {current[1]}",picker))
                candidates = []
                for effect in options[slot]:
                    if effect in values[:slot]+values[slot+1:]:
                        continue
                    updated = list(values);updated[slot]=effect
                    candidates.append(entry(*LABELS[effect],name(updated)))
                updated=list(values);updated[slot]=0
                candidates += [entry("清除此词条","Clear this effect",name(updated)),
                               entry("返回","Back",page)]
                pages[picker] = dict(back=page,entries=candidates)
            if all(values):
                canonical=tuple(sorted(values,key=lambda x:(int(planner.effects[x]["overrideBaseEffectId"]),x)))
                shop=product_index[(kind,canonical)]
                purchase=page+"_purchase"
                purchases[purchase] = dict(shop_id=shop,back=page)
                choices.append(entry("确定制作（1 暗痕）","Craft (1 Murk)",purchase))
            else:
                choices.append(entry("确定制作（请先选满三条）","Craft (select all three first)",page))
            choices.append(entry("返回","Back","select"))
            pages[page] = dict(back="select",entries=choices,editor=number,selection=list(values))
    pages["select"]["entries"].append(entry("返回","Back","root"))
    allocation={}
    counter=STATE_BASE
    for name in pages:
        allocation[name]=counter;counter+=4
    allocation["original_shop"]=counter;counter+=1
    for name in purchases:
        allocation[name]=counter;counter+=1
    allocation["exit"]=10
    for name,p in pages.items():
        p["name"]=name;p["state"]=allocation[name];p["back"]=allocation[p["back"]]
        for e in p["entries"]:
            e["target"]=allocation[e["target"]]
    for name,p in purchases.items():
        p["state"]=allocation[name];p["back"]=allocation[p["back"]]
    plan=dict(schema_version=1,source_sha256=SOURCE,regulation_internal_version="10350000",
        root_state=allocation["root"],original_shop_state=allocation["original_shop"],
        state_first=STATE_BASE,state_end=counter,pages=list(pages.values()),purchases=list(purchases.values()),
        texts=texts,products=products,price=1,currency_cost_type=4,
        shop_template_id=10041,
        shop_template_guard={f:int(shop_index[10041][f]) for f in ("equipId","equipType","costType","value","sellQuantity","eventFlag_forStock","eventFlag_forRelease")},
        slots=dict(normal_candidates=list(NORMAL),deep_first=list(DEEP_FIRST),deep_other=list(DEEP_FREE),bound_curse=CURSE),
        limitations=["Drafts last only while editing that relic; returning to the four-entry menu resets drafts",
                     "Craft opens a native single-product purchase confirmation at 1 Murk",
                     "New relic definition IDs require keeping this mod installed; vanilla rollback is not provided",
                     "Candidate subset only; deep slot 1 binds a curse, slots 2 and 3 use native curse-free pools",
                     "Daily normal/deep difficulty budgets are not enforced by this editor; multiplayer unsupported",
                     "Repeat crafting stock behavior and new relic IDs require in-game verification"])
    audit_plan(plan)
    return plan


def audit_plan(plan):
    products = {p["shop_id"]:p for p in plan["products"]}
    if len(products)!=len(plan["products"]) or len({p["relic_id"] for p in products.values()})!=len(products):
        raise ValueError("Duplicate product allocation")
    if plan["price"]!=1 or plan["currency_cost_type"]!=4:
        raise ValueError("Incorrect price/currency")
    for product in products.values():
        effects=product["effects"]
        if len(effects)!=3 or len(set(effects))!=3:
            raise ValueError("Relic needs three distinct effects")
        if product["kind"]=="normal":
            if not set(effects)<=set(NORMAL) or product["curses"]!=[None,None,None]:
                raise ValueError("Invalid ordinary relic effects")
        elif product["kind"]=="deep":
            if effects[0] not in DEEP_FIRST or not set(effects[1:])<=set(DEEP_FREE) or product["curses"]!=[CURSE,None,None]:
                raise ValueError("Invalid deep relic binding")
        else:
            raise ValueError("Unknown relic kind")
    nodes={10,plan["original_shop_state"]}
    for page in plan["pages"]:
        if not 1<=len(page["entries"])<=10:
            raise ValueError("Unsupported native menu length")
        if nodes.intersection(range(page["state"],page["state"]+4)):
            raise ValueError("Overlapping state allocation")
        nodes.update(range(page["state"],page["state"]+4))
        if "editor" in page and len(page["entries"])!=5:
            raise ValueError("Editor must have exactly five entries")
    for purchase in plan["purchases"]:
        if purchase["state"] in nodes or purchase["shop_id"] not in products:
            raise ValueError("Invalid purchase node")
        nodes.add(purchase["state"])
    entry_nodes={10,plan["original_shop_state"]}|{p["state"] for p in plan["pages"]}|{p["state"] for p in plan["purchases"]}
    for page in plan["pages"]:
        if page["back"] not in entry_nodes or any(e["target"] not in entry_nodes for e in page["entries"]):
            raise ValueError("Dangling menu transition")
    for purchase in plan["purchases"]:
        if purchase["back"] not in entry_nodes:
            raise ValueError("Dangling shop return")
    texts={t["id"] for t in plan["texts"]}
    if len(texts)!=len(plan["texts"]) or any(e["text_id"] not in texts for p in plan["pages"] for e in p["entries"]):
        raise ValueError("Text references invalid")
    owners={p["editor"] for p in plan["pages"] if "editor" in p}
    if owners!={0,1,2,3}:
        raise ValueError("Expected two normal and two deep editors")
    # Every generated page's only outgoing dispatcher runs after the native modal wait.
    # Shop nodes likewise retain the original shop-close condition; no tick polling or recursion is emitted.
    purchase_map={p["state"]:p for p in plan["purchases"]}
    for page in plan["pages"]:
        if "selection" not in page:
            continue
        selection=page["selection"]
        if len(selection)!=3 or len([x for x in selection if x])!=len(set(x for x in selection if x)):
            raise ValueError("Duplicate selected effects")
        craft=page["entries"][3]["target"]
        if not all(selection):
            if craft!=page["state"]: raise ValueError("Incomplete draft can purchase")
        else:
            if craft not in purchase_map: raise ValueError("Completed draft has no purchase")
            product=products[purchase_map[craft]["shop_id"]]
            if set(selection)!=set(product["effects"]): raise ValueError("Wrong crafted effects")
            if product["kind"]!=("normal" if page["editor"]<2 else "deep"): raise ValueError("Normal/deep crossed")
    return True


def build(root=ROOT,shell=None):
    root=Path(root).resolve()
    verify=load(root/"local/evidence/relic-export-verification.json")
    if verify["status"]!="PASS" or verify["regulation_sha256"]!=SOURCE:
        raise ValueError("Relic exports unverified")
    for table in verify["tables"]:
        if sha(root/"local/evidence"/(table["table"]+".csv"))!=table["csv_sha256"]:
            raise ValueError("Relic export changed")
    def csv_rows(name):
        with (root/"local/evidence"/(name+".csv")).open(encoding="utf-8-sig",newline="") as f:
            return list(csv.DictReader(f))
    plan=compile_plan(load(root/"local/evidence/relic-catalog.json"),load(root/"data/relic_budgets.json"),
                      csv_rows("ShopLineupParam"),csv_rows("EquipParamAntique"))
    rewards=Path(load(root/"local/phase1/tiered_choices-package.json")["path"])
    reward_meta=verify_package(rewards,root)
    if reward_meta.get("kind")!="native_rewards": raise ValueError("Expected native reward package")
    folder=root/"local/packages"/("relic_editor_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(rewards/"mod/regulation.bin",folder/"reward-base.bin")
    if sha(folder/"reward-base.bin")!=reward_meta["sha256"]["mod/regulation.bin"]: raise ValueError("Reward input changed")
    plan["reward_sha256"]=sha(folder/"reward-base.bin")
    (folder/"editor-plan.json").write_text(json.dumps(plan,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    shell=shell or shutil.which("pwsh")
    if not shell: raise ValueError("PowerShell7 is required")
    process=subprocess.run([shell,"-NoProfile","-File",str(root/"tools/build_relic_editor.ps1"),
        "-ProjectRoot",str(root),"-Plan",str(folder/"editor-plan.json"),
        "-RewardBase",str(folder/"reward-base.bin"),"-OutputDirectory",str(folder/"mod")],
        capture_output=True,text=True,encoding="utf-8",errors="replace",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    (folder/"build.log").write_text(process.stdout+"\n"+process.stderr,encoding="utf-8")
    if process.returncode: raise ValueError("Editor build failed: "+str(folder/"build.log"))
    save="NRE_"+folder.name+".sl2"
    common=f'profileVersion = "v1"\nsavefile = "{save}"\nstart_online = false\n[[supports]]\ngame = "nightreign"\n'
    profile=common+'[[packages]]\nid = "NRE-Relic-Editor"\nsource = "./mod"\n'
    for name in ("generate.me3","play.me3"): (folder/name).write_text(profile,encoding="utf-8")
    (folder/"manifest.json").write_text(json.dumps(dict(schema_version=1,source_sha256=SOURCE,
        regulation_internal_version="10350000",archive_header_sha256=ARCHIVE_HASH,
        game_verified=False,limitations=plan["limitations"]),ensure_ascii=False,indent=2),encoding="utf-8")
    files=["generate.me3","play.me3","manifest.json","editor-plan.json","reward-base.bin","mod/editor-report.json","mod/regulation.bin"]+["mod/"+a for a in ASSETS]
    (folder/"package.json").write_text(json.dumps(dict(schema_version=1,kind="relic_editor",savefile=save,
        sha256={f:sha(folder/f) for f in files}),indent=2),encoding="utf-8")
    verify_package(folder,root)
    (root/"local/relic-editor-package.json").write_text(json.dumps({"path":str(folder)},ensure_ascii=False),encoding="utf-8")
    return folder


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("build","launch"))
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--pwsh")
    args=parser.parse_args()
    if args.action=="build": print(build(args.root,args.pwsh))
    else:
        folder=Path(load(args.root/"local/relic-editor-package.json")["path"])
        if verify_package(folder,args.root).get("kind")!="relic_editor": raise ValueError("Expected relic editor")
        print(launch(folder,True,args.root))
