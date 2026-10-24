"""Conservative preset planner backed by actual native relic pools."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = ["Wylder", "Guardian", "Ironeye", "Duchess", "Raider",
              "Revenant", "Recluse", "Executor", "Scholar", "Undertaker"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def catalog_hash(catalog):
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


class Planner:
    def __init__(self, catalog, budgets):
        self.catalog, self.budgets = catalog, budgets
        self.effects = {int(e["ID"]): e for e in catalog["effects"]}
        self.templates = {t["id"]: t for t in catalog["templates"]}
        self.normal = set()
        self.fixed_pools = {}
        def active(pool_id):
            return {r["effect_id"] for r in catalog["pools"].get(str(pool_id),[])
                    if r["weight"]>0 and (r["dlc_weight_raw"]==-1 or r["dlc_weight_raw"]>0)
                    and r["effect_id"] in self.effects}
        self.curse_required = active(2000000)
        self.curse_free = active(2200000)
        self.curses = {key for key in active(3000000) if self.effects[key]["isDebuff"]=="1"}
        self.deep = (self.curse_required | self.curse_free) - (self.curse_required & self.curse_free)
        for key, entries in catalog["pools"].items():
            # Experimental application only uses one-row pools whose DLC branch
            # cannot name a different effect. Weight semantics still require game tests.
            if len(entries) == 1 and entries[0]["weight"] > 0 and entries[0]["dlc_weight_raw"] in (-1, entries[0]["weight"]):
                self.fixed_pools.setdefault(entries[0]["effect_id"], int(key))
        approved_templates = set(budgets.get("catalog_policy", {}).get("normal_template_ids", []))
        for t in catalog["templates"]:
            if t["deep_raw"] != 0 or t["id"] not in approved_templates:
                continue
            for field, pool_id in t["pool_links"].items():
                if "curse" in field or pool_id < 0:
                    continue
                for row in catalog["pools"].get(str(pool_id), []):
                    effect_id = row["effect_id"]
                    if row["weight"] > 0 and effect_id in self.effects and self.effects[effect_id]["isDebuff"] == "0":
                        self.normal.add(effect_id)

    def new(self, character="Ironeye", mode="normal", depth=None):
        return {"schema_version": 1, "character": character, "mode": mode, "depth": depth,
                "catalog_hash": catalog_hash(self.catalog),
                "normal_effects": [], "deep_templates": [], "deep_bundles": [],
                "status": "draft_not_applicable"}

    def deep_effects(self, template_id):
        t = self.templates.get(template_id)
        if not t or t["deep_raw"] != 1:
            raise ValueError("必须选择原生深夜遗物模板")
        result, positive, negative = [], 0, 0
        for field, pool_id in t["pool_links"].items():
            if pool_id < 0:
                continue
            entries = self.catalog["pools"].get(str(pool_id), [])
            # No random pool may silently become a claimed exact combination.
            ids = {r["effect_id"] for r in entries if r["weight"] > 0}
            if len(ids) != 1 or len(entries) != 1:
                raise ValueError("深夜模板含随机池，不能当作精确自选组合")
            effect_id = next(iter(ids))
            if effect_id not in self.effects:
                raise ValueError("深夜模板效果引用未解析")
            result.append(effect_id)
            if "curse" in field:
                negative += 1
            else:
                positive += 1
        if not positive or not negative:
            raise ValueError("深夜模板缺少完整正负绑定，暂不开放")
        return result, positive

    def validate(self, preset):
        errors, selected = [], []
        if not isinstance(preset,dict):
            return {"valid_draft":False,"errors":["预设必须是JSON对象"],"game_applicable":False}
        required={"schema_version","character","mode","depth","catalog_hash","normal_effects","deep_templates"}
        if not required.issubset(preset):
            return {"valid_draft":False,"errors":["预设缺少必需字段"],"game_applicable":False}
        if preset.get("schema_version") != 1:
            errors.append("不支持的预设格式")
        if preset.get("catalog_hash") != catalog_hash(self.catalog):
            errors.append("目录版本不匹配，请重新审核预设")
        character = preset.get("character")
        if character not in CHARACTERS:
            errors.append("未知职业")
        mode, depth = preset.get("mode"), preset.get("depth")
        if mode == "normal" and depth is None:
            budget = self.budgets["normal"]
        elif mode == "deep" and str(depth) in self.budgets["depths"]:
            budget = self.budgets["depths"][str(depth)]
        else:
            errors.append("模式或深度无效")
            budget = {"normal": 0, "deep": 0}
        normal, deep = preset.get("normal_effects", []), preset.get("deep_templates", [])
        bundles=preset.get("deep_bundles",[])
        if not isinstance(normal, list) or not isinstance(deep, list) or not isinstance(bundles,list):
            return {"valid_draft": False, "errors": ["词条列表格式错误"], "game_applicable": False}
        if len(normal) > budget["normal"]:
            errors.append("普通词条超出设计额度")
        for effect_id in normal:
            if type(effect_id) is not int or effect_id not in self.normal:
                errors.append(f"不在已解析普通词条池: {effect_id}")
            else:
                selected.append(effect_id)
        deep_cost = 0
        for template_id in deep:
            try:
                if type(template_id) is not int:
                    raise ValueError("模板ID格式错误")
                ids, cost = self.deep_effects(template_id)
                selected.extend(ids)
                deep_cost += cost
            except ValueError as exc:
                errors.append(str(exc))
        for bundle in bundles:
            if not isinstance(bundle,dict):
                errors.append("深夜正负绑定格式错误");continue
            positive,negative=bundle.get("effect_id"),bundle.get("curse_id")
            if type(positive) is not int or positive not in self.deep:
                errors.append("深夜正面词条不属于已追踪的池");continue
            selected.append(positive);deep_cost+=1
            if positive in self.curse_required:
                if type(negative) is not int or negative not in self.curses:
                    errors.append("此深夜词条必须绑定一条有效负面效果")
                else:
                    selected.append(negative)
            elif negative is not None:
                errors.append("此深夜词条来自无负面池，不允许自行加配负面")
        if (deep or bundles) and mode != "deep":
            errors.append("普通模式不允许深夜模板")
        if deep_cost > budget["deep"]:
            errors.append("深夜正面词条超出设计额度")
        # These are intentionally conservative planner rules, not decoded native rules.
        seen, compat, exclusive = set(), set(), set()
        for effect_id in selected:
            e = self.effects[effect_id]
            if effect_id in seen:
                errors.append(f"重复词条暂不开放: {effect_id}")
            seen.add(effect_id)
            if character in CHARACTERS and e.get("allow" + character) != "1":
                errors.append(f"职业标志不允许: {effect_id}")
            for field, used in (("compatibilityId", compat), ("exclusivityId", exclusive)):
                value = int(e[field])
                if value >= 0:
                    if value in used:
                        errors.append(f"相同{field}分组，保守拒绝: {value}")
                    used.add(value)
        return {"valid_draft": not errors, "errors": errors, "game_applicable": False,
                "normal_used": len(normal), "deep_used": deep_cost, "budget": budget,
                "limitations": ["额度为任务书设计值", "重复与同分组保守拒绝，原生合法上限尚未解码",
                                "通过仅表示草稿约束通过，不代表游戏内合法性或同步已验证"]}

    def save(self, preset, path):
        verdict = self.validate(preset)
        if not verdict["valid_draft"]:
            raise ValueError("；".join(verdict["errors"]))
        payload = dict(preset, status="draft_not_applicable")
        # Refuse replacement; UI asks users to choose a new preset file.
        with Path(path).open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)

    def experimental_manifest(self, preset, carrier_id):
        verdict = self.validate(preset)
        if not verdict["valid_draft"]:
            raise ValueError("；".join(verdict["errors"]))
        if preset["mode"] != "normal" or preset["deep_templates"] or preset.get("deep_bundles"):
            raise ValueError("首个游戏应用实验只开放普通词条")
        carrier = self.templates.get(carrier_id)
        if not carrier or carrier["deep_raw"] != 0:
            raise ValueError("需要已存在的普通遗物载体")
        if any(v >= 0 for k,v in carrier["pool_links"].items() if "curse" in k):
            raise ValueError("载体具有负面绑定，不能覆盖")
        effects = preset["normal_effects"]
        if not 1 <= len(effects) <= 3:
            raise ValueError("单遗物实验需要1–3条普通词条")
        changes=[]
        for i in range(1,4):
            field=f"attachEffectTableId_{i}"
            old=carrier["pool_links"][field]
            new=-1
            if i <= len(effects):
                new=self.fixed_pools.get(effects[i-1])
                if new is None:
                    raise ValueError(f"没有可复用的确定性原生池: {effects[i-1]}")
            if old != new:
                changes.append({"table":"EquipParamAntique","row_id":carrier_id,
                                "field":field,"before":old,"after":new})
        if not changes:
            raise ValueError("选择与原载体相同，没有实验差异")
        return {"schema_version":1,"source_sha256":self.catalog["regulation_sha256"],
                "regulation_internal_version":"10350000","status":"EXPERIMENT_ONLY",
                "carrier_id":carrier_id,"preset":preset,"changes":changes,
                "limitations":["仅用于隔离存档的商品/新生成遗物实验",
                               "既有物品是否改变、卸除清理及多人独立性均未验证"]}

    def native_slot_assignment(self, effect_ids, color, excluded_templates=()):
        """Find a real randomized template accepting every slot in both weight views.

        This is parameter evidence, not certification by the game or servers.
        """
        if not 1 <= len(effect_ids) <= 3 or len(set(effect_ids)) != len(effect_ids):
            raise ValueError("每件遗物需要1–3条不同词条")
        try:
            ordered = sorted(effect_ids, key=lambda key: (
                int(self.effects[key]["overrideBaseEffectId"]), key))
        except KeyError:
            raise ValueError("效果排序字段或ID缺失")
        for template in sorted(self.templates.values(), key=lambda t: t["id"]):
            if template["id"] in excluded_templates:
                continue
            if template["deep_raw"] != 0 or template["color_raw"] != color:
                continue
            links=template["pool_links"]
            if any(v>=0 for k,v in links.items() if "curse" in k):
                continue
            pool_ids=[links[f"attachEffectTableId_{i}"] for i in range(1,4)]
            active=[v for v in pool_ids if v>=0]
            if len(active)!=len(ordered):
                continue
            # Use only traced ordinary lottery pools, excluding named/fixed relics.
            if any(v not in (100,200,300,110,210,310) for v in active):
                continue
            accepted=True
            for pool_id,effect_id in zip(active,ordered):
                rows=self.catalog["pools"].get(str(pool_id),[])
                candidates=[r for r in rows if r["effect_id"]==effect_id]
                if not any(r["weight"]>0 and (r["dlc_weight_raw"]==-1 or r["dlc_weight_raw"]>0)
                           for r in candidates):
                    accepted=False
                    break
            if accepted:
                return {"template_id":template["id"],"color_raw":color,
                        "effect_ids":ordered,"original_pool_ids":active,
                        "status":"NATIVE_POOL_MATCH_GAME_UNVERIFIED"}
        raise ValueError("未找到每个槽位均允许所选词条的普通随机遗物模板")

    def experimental_random_manifest(self,preset,color,shop_row,excluded_templates=()):
        result=self.validate(preset)
        if not result["valid_draft"]:
            raise ValueError("；".join(result["errors"]))
        if preset["mode"]!="normal" or preset["deep_templates"] or preset.get("deep_bundles"):
            raise ValueError("当前随机载体构建只支持普通模式")
        if str(shop_row["equipType"])!="4":
            raise ValueError("商店目标不是遗物")
        assignment=self.native_slot_assignment(preset["normal_effects"],color,excluded_templates)
        ordered=dict(preset,normal_effects=assignment["effect_ids"])
        manifest=self.experimental_manifest(ordered,assignment["template_id"])
        manifest["changes"].append({"table":"ShopLineupParam","row_id":int(shop_row["ID"]),
            "field":"equipId","before":int(shop_row["equipId"]),"after":assignment["template_id"]})
        manifest["native_slot_assignment"]=assignment
        manifest["limitations"]=["参数级原生池匹配已检查，仍需游戏获得/装备/卸除及重载验证",
            "生成期间目标随机遗物模板全局变化，只在隔离单人测试使用；不支持多人独立配置"]
        return manifest

    def experimental_loadout_manifest(self,preset,shop_rows):
        result=self.validate(preset)
        if not result["valid_draft"]:
            raise ValueError("；".join(result["errors"]))
        if preset["mode"]!="normal" or preset.get("deep_bundles") or preset["deep_templates"]:
            raise ValueError("当前游戏构建只开放普通模式；深夜仍处于配置验证")
        chosen=preset["normal_effects"]
        if not 1<=len(chosen)<=6:
            raise ValueError("普通实验包支持1–6条，分配到最多两件遗物")
        pieces=(len(chosen)+2)//3
        # Green is an observed working shop route. No vessel colors are changed.
        stands=[s for s in self.catalog.get("stands",[])
                if s["Name"].startswith("["+preset["character"]+"]")
                and sum(str(s.get(f"relicSlot{i}")) in ("3","4") for i in range(1,4))>=pieces]
        if not stands:
            raise ValueError("未找到该职业可容纳所需绿色遗物的原生容器")
        needed=[10041,10032][:pieces]
        indexed={int(row["ID"]):row for row in shop_rows}
        if any(key not in indexed for key in needed):
            raise ValueError("商店导出缺少实验入口")
        merged=None;excluded=set();assignments=[]
        for i,shop_id in enumerate(needed):
            part=dict(preset,normal_effects=chosen[i*3:(i+1)*3])
            manifest=self.experimental_random_manifest(part,3,indexed[shop_id],excluded)
            excluded.add(manifest["carrier_id"])
            assignments.append({"shop_row_id":shop_id,
                "original_item_id":int(indexed[shop_id]["equipId"]),
                **manifest["native_slot_assignment"]})
            if merged is None:
                merged=dict(manifest)
                merged["changes"]=list(manifest["changes"])
            else:
                merged["changes"].extend(manifest["changes"])
        merged["preset"]=preset
        merged["loadout_assignments"]=assignments
        merged["compatible_vessels"]=[{"id":int(s["ID"]),"name":s["Name"],
            "colors":[int(s[f"relicSlot{i}"]) for i in range(1,4)]} for s in stands]
        merged["limitations"]+=["商店两件商品须仍有库存；需要拥有列表中的适配容器",
                               "两件联合使用尚需独立实机验证，不因单件通过而自动视为通过"]
        return merged

    def experimental_deep_manifest(self,preset,color,shop_row):
        verdict=self.validate(preset)
        if not verdict["valid_draft"]:
            raise ValueError("；".join(verdict["errors"]))
        bundles=preset.get("deep_bundles",[])
        if preset["mode"]!="deep" or preset["normal_effects"] or preset["deep_templates"] or not 1<=len(bundles)<=3:
            raise ValueError("深夜单件实验仅接受1–3组正负绑定，普通词条需单独生成")
        if str(shop_row["equipType"])!="4":
            raise ValueError("商店目标不是遗物")
        ordered=sorted(bundles,key=lambda b:(int(self.effects[b["effect_id"]]["overrideBaseEffectId"]),b["effect_id"]))
        def member(pool_id,effect_id):
            return any(r["effect_id"]==effect_id and r["weight"]>0
                       and (r["dlc_weight_raw"]==-1 or r["dlc_weight_raw"]>0)
                       for r in self.catalog["pools"].get(str(pool_id),[]))
        for template in sorted(self.templates.values(),key=lambda t:t["id"]):
            if template["deep_raw"]!=1 or template["color_raw"]!=color:
                continue
            links=template["pool_links"]
            if sum(links[f"attachEffectTableId_{i}"]>=0 for i in range(1,4))!=len(ordered):
                continue
            matched=True;changes=[]
            for i,bundle in enumerate(ordered,1):
                positive,negative=bundle["effect_id"],bundle["curse_id"]
                field=f"attachEffectTableId_{i}";curse_field=f"attachEffectTableId_curse{i}"
                if not member(links[field],positive):
                    matched=False;break
                if negative is None:
                    if links[curse_field]>=0:
                        matched=False;break
                elif not member(links[curse_field],negative):
                    matched=False;break
                for target,value in ((field,positive),(curse_field,negative)):
                    if value is None:continue
                    pool=self.fixed_pools.get(value)
                    if pool is None:
                        matched=False;break
                    if pool!=links[target]:
                        changes.append({"table":"EquipParamAntique","row_id":template["id"],
                                        "field":target,"before":links[target],"after":pool})
                if not matched:break
            if matched:
                changes.append({"table":"ShopLineupParam","row_id":int(shop_row["ID"]),
                    "field":"equipId","before":int(shop_row["equipId"]),"after":template["id"]})
                return {"schema_version":1,"source_sha256":self.catalog["regulation_sha256"],
                    "regulation_internal_version":"10350000","status":"DEEP_EXPERIMENT_ONLY",
                    "carrier_id":template["id"],"preset":preset,"ordered_bundles":ordered,
                    "changes":changes,"limitations":["深夜原生池逐槽匹配，尚未实机验证",
                        "保留所有原生正负面绑定；需要深夜容器/模式实际装备测试",
                        "仅隔离单人，不支持普通与深夜混合打包或多人"] }
        raise ValueError("没有同时满足正面槽与负面槽的原生深夜模板")

    def experimental_combined_manifest(self,preset,shop_rows):
        if preset["mode"]=="normal":
            return self.experimental_loadout_manifest(preset,shop_rows)
        verdict=self.validate(preset)
        if not verdict["valid_draft"]:
            raise ValueError("；".join(verdict["errors"]))
        if preset["deep_templates"]:
            raise ValueError("组合打包请使用逐条正负绑定")
        bundles=preset.get("deep_bundles",[])
        if not preset["normal_effects"] and not bundles:
            raise ValueError("没有选择词条")
        normal_count=(len(preset["normal_effects"])+2)//3
        deep_count=(len(bundles)+2)//3
        vessels=[s for s in self.catalog.get("stands",[])
            if s["Name"].startswith("["+preset["character"]+"]")
            and sum(str(s.get(f"relicSlot{i}")) in ("3","4") for i in range(1,4))>=normal_count
            and sum(str(s.get(f"deepRelicSlot{i}")) in ("3","4") for i in range(1,4))>=deep_count]
        if not vessels:
            raise ValueError("没有同时适配普通和深夜绿色槽数量的原生容器")
        indexed={int(r["ID"]):r for r in shop_rows}
        chunks=[];assignments=[]
        if preset["normal_effects"]:
            normal=dict(preset,mode="normal",depth=None,deep_bundles=[],deep_templates=[])
            manifest=self.experimental_loadout_manifest(normal,shop_rows)
            chunks.append(manifest)
            assignments.extend(dict(a,kind="normal") for a in manifest["loadout_assignments"])
        for index in range(deep_count):
            shop_id=[10036,10037][index]
            if shop_id not in indexed:
                raise ValueError("缺少深夜生成使用的商店入口")
            part=dict(preset,normal_effects=[],deep_bundles=bundles[index*3:(index+1)*3])
            manifest=self.experimental_deep_manifest(part,3,indexed[shop_id])
            chunks.append(manifest)
            assignments.append({"kind":"deep","shop_row_id":shop_id,
                "original_item_id":int(indexed[shop_id]["equipId"]),
                "template_id":manifest["carrier_id"],"color_raw":3,
                "effect_ids":[b["effect_id"] for b in manifest["ordered_bundles"]],
                "curse_ids":[b["curse_id"] for b in manifest["ordered_bundles"]]})
        result=dict(chunks[0])
        result["changes"]=[change for chunk in chunks for change in chunk["changes"]]
        keys=[(c["table"],c["row_id"],c["field"]) for c in result["changes"]]
        if len(set(keys))!=len(keys):
            raise ValueError("生成目标冲突，不能合并")
        result["status"]="COMBINED_DEEP_EXPERIMENT_ONLY"
        result["preset"]=preset;result["loadout_assignments"]=assignments
        result["compatible_vessels"]=[{"id":int(s["ID"]),"name":s["Name"],
            "colors":[int(s[f"relicSlot{i}"]) for i in range(1,4)],
            "deep_colors":[int(s[f"deepRelicSlot{i}"]) for i in range(1,4)]} for s in vessels]
        result["limitations"]=["按原生正负槽逐一匹配；深夜及混合装配仍需实机验证",
            "所有商品需有库存，需拥有适配容器；仅在隔离单人存档生成",
            "先使用生成配置获得物品，再切换无补丁配置；不支持多人生成"]
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT/"local/evidence/relic-catalog.json")
    parser.add_argument("--preset", type=Path, required=True)
    args = parser.parse_args()
    planner = Planner(load(args.catalog), load(ROOT/"data/relic_budgets.json"))
    verdict = planner.validate(load(args.preset))
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    raise SystemExit(0 if verdict["valid_draft"] else 1)


if __name__ == "__main__":
    main()
