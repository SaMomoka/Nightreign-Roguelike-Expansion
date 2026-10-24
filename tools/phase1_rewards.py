"""Native Nightreign reward-pool adapter; no simulated gameplay or live hooks."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268"
TABLES = ("ItemTableParam", "EquipParamGoods", "PermanentBuffParam",
          "SpEffectParam", "ItemLotParam_enemy", "NpcParam")
MODES = ("weighted", "three_choices_probe", "distinct_choices", "tiered_choices")
FAMILY_POOLS = (4200101, 4200102, 4200103)
GUARD_FIELDS = ("itemId", "itemCategory", "quantity", "onlyForClass",
                "eventFlagId", "disableParam_NT", "unknown_6", "unknown_7")


def audit_choice_families(tables, pool_ids=FAMILY_POOLS):
    """Prove pairwise-disjoint goods AND effect identities, independent of RNG."""
    families, seen_goods, seen_effects = [], set(), set()
    for pool_id in pool_ids:
        rows = [r for r in tables["ItemTableParam"] if int(r["ID"]) == pool_id
                and int(r["chanceWeight"]) > 0]
        if not rows:
            raise ValueError("Empty choice family")
        goods_ids, effect_ids = set(), set()
        for row in rows:
            if int(row["itemCategory"]) != 1:
                raise ValueError("Choice family contains a nested or non-goods entry")
            if int(row["quantity"]) != 1 or int(row["onlyForClass"]) != 0 or int(row["eventFlagId"]) != 0:
                raise ValueError("Conditional family member requires new eligibility research")
            goods_id = int(row["itemId"])
            if goods_id in goods_ids:
                raise ValueError("Repeated family member")
            good = unique(tables["EquipParamGoods"], goods_id)
            if int(good["goodsType"]) != 11:
                raise ValueError("Family member is not permanent buff")
            permanent = unique(tables["PermanentBuffParam"], int(good["vagrantItemLotId"]))
            effect_id = int(permanent["spEffectId"])
            unique(tables["SpEffectParam"], effect_id)
            goods_ids.add(goods_id)
            effect_ids.add(effect_id)
        if goods_ids & seen_goods or effect_ids & seen_effects:
            raise ValueError("Choice families overlap by good or effect")
        seen_goods.update(goods_ids)
        seen_effects.update(effect_ids)
        families.append(dict(pool_id=pool_id, goods_ids=sorted(goods_ids),
                             sp_effect_ids=sorted(effect_ids), native_members=len(rows)))
    return families


def audit_reward_scope(tables, pool_ids):
    """Report direct references only; script references remain outside this audit."""
    scopes = []
    for pool_id in pool_ids:
        table_refs = [int(r["ID"]) for r in tables["ItemTableParam"]
                      if int(r["itemCategory"]) == 7 and int(r["itemId"]) == pool_id]
        lot_refs = []
        for row in tables["ItemLotParam_enemy"]:
            for slot in range(1, 9):
                suffix = "%02d" % slot
                if int(row["lotItemCategory" + suffix]) == 7 and int(row["lotItemId" + suffix]) == pool_id:
                    lot_refs.append({"row_id": int(row["ID"]), "slot": slot})
        scopes.append(dict(pool_id=pool_id, parent_tables=sorted(set(table_refs)),
                           enemy_lot_reference_count=len(lot_refs),
                           enemy_lot_references=lot_refs))
    return {"before_patch": scopes,
            "scope": "Direct ItemTable and enemy ItemLot references only; not an exhaustive script/map reachability audit",
            "fort_base_npcs": [int(r["ID"]) for r in tables.get("NpcParam", [])
                              if r.get("rewardItemLot_1") == "6000050" or r.get("rewardItemLot_2") == "6000050"]}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_tables(root):
    evidence = root / "local/evidence"
    verified = read_json(evidence / "phase1-export-verification.json")
    if verified["status"] != "PASS" or verified["regulation_sha256"] != SOURCE:
        raise ValueError("Unverified regulation export")
    checks = {r["table"]: r for r in verified["tables"]}
    tables = {}
    for name in TABLES:
        path = evidence / (name + ".csv")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.upper() != checks[name]["csv_sha256"].upper():
            raise ValueError("Export changed: " + name)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            tables[name] = list(csv.DictReader(stream))
    return tables


def unique(rows, row_id):
    matches = [r for r in rows if int(r["ID"]) == row_id]
    if len(matches) != 1:
        raise ValueError("Expected unique row: " + str(row_id))
    return matches[0]


def compile_manifest(config, tables, mode="weighted"):
    if mode not in MODES:
        raise ValueError("Unknown experiment mode")
    if mode == "tiered_choices":
        from reward_tiers import compile_tiered
        return compile_tiered(config,tables)
    if config["schema_version"] != 1 or config["source_sha256"] != SOURCE:
        raise ValueError("Unsupported source/configuration")
    # This adapter only supports the audited pool and route, not arbitrary IDs.
    if config["pool_id"] != 4200100:
        raise ValueError("Unsupported native pool")
    entries = config["buffs"]
    ids = [entry["goods_id"] for entry in entries]
    if len(ids) != len(set(ids)) or len(ids) != 6:
        raise ValueError("Expected six distinct native buffs")
    expected_ids = {8000000, 8010000, 8020000, 8100000, 8200000, 8200500}
    if set(ids) != expected_ids:
        raise ValueError("Unreviewed buff mapping")
    changes, audit = [], []
    families = audit_choice_families(tables) if mode == "distinct_choices" else []
    active_pools = FAMILY_POOLS if families else (config["pool_id"],)
    pool = [(i, r) for i, r in enumerate(tables["ItemTableParam"])
            if int(r["ID"]) in active_pools]
    if not pool:
        raise ValueError("Missing pool")
    for entry in entries:
        weight = entry["weight"]
        if type(weight) is not int or not 1 <= weight <= 65535:
            raise ValueError("Weight must be an integer in 1..65535")
        goods = unique(tables["EquipParamGoods"], entry["goods_id"])
        if int(goods["goodsType"]) != 11:
            raise ValueError("Not a native permanent buff good")
        permanent = unique(tables["PermanentBuffParam"], int(goods["vagrantItemLotId"]))
        effect = unique(tables["SpEffectParam"], int(permanent["spEffectId"]))
        if int(permanent["ID"]) != entry["permanent_buff_id"] or int(effect["ID"]) != entry["sp_effect_id"]:
            raise ValueError("Buff reference changed")
        values = {}
        for field, value in entry["effect_fields"].items():
            if float(effect[field]) != value:
                raise ValueError("Native effect value changed: " + field)
            values[field] = value
        matches = [(i, r) for i, r in pool
                   if int(r["itemCategory"]) == 1 and int(r["itemId"]) == entry["goods_id"]]
        if len(matches) != 1:
            raise ValueError("Ambiguous or missing pool member")
        ordinal, row = matches[0]
        before = int(row["chanceWeight"])
        if before != weight:
            changes.append(dict(table="ItemTableParam", row_id=int(row["ID"]),
                                row_ordinal=ordinal, field="chanceWeight", before=before,
                                after=weight, guard={k: int(row[k]) for k in GUARD_FIELDS}))
        audit.append(dict(id=entry["id"], name=entry["name"], goods_id=entry["goods_id"],
                          permanent_buff_id=int(permanent["ID"]), sp_effect_id=int(effect["ID"]),
                          fields=values, game_verified=False))
    if mode in ("three_choices_probe", "distinct_choices"):
        # Redirect only the existing positive table references in two fort reward rows.
        # Leave base points, quantity, flags and the third native reward row intact.
        route_rows = (6000050, 6000051, 6000052) if families else (6000050, 6000051)
        for route_index, row_id in enumerate(route_rows):
            row = unique(tables["ItemLotParam_enemy"], row_id)
            destination = FAMILY_POOLS[route_index] if families else config["pool_id"]
            for slot in range(1, 9):
                suffix = "%02d" % slot
                key, cat, chance = ("lotItemId" + suffix, "lotItemCategory" + suffix,
                                    "lotItemBasePoint" + suffix)
                if int(row[chance]) > 0:
                    if int(row[cat]) != 7:
                        raise ValueError("Unexpected non-table reward route")
                    changes.append(dict(table="ItemLotParam_enemy", row_id=row_id,
                                        field=key, before=int(row[key]), after=destination,
                                        guard={cat: 7, chance: int(row[chance])}))
        third = unique(tables["ItemLotParam_enemy"], 6000052)
        if third["lotItemId01"] != str(config["pool_id"]) or third["lotItemCategory01"] != "7":
            raise ValueError("Native third reward route changed")
    if not changes:
        raise ValueError("No patch changes")
    new_weights = {entry["goods_id"]: entry["weight"] for entry in entries}
    total_before = sum(int(r["chanceWeight"]) for _, r in pool)
    total_after = sum(new_weights.get(int(r["itemId"]), int(r["chanceWeight"]))
                      if int(r["itemCategory"]) == 1 else int(r["chanceWeight"]) for _, r in pool)
    return dict(schema_version=1, source_sha256=SOURCE, regulation_internal_version="10350000",
                experiment="PHASE1-" + mode, changes=changes,
                native_buffs=audit, pool_weight_before=total_before, pool_weight_after=total_after,
                choice_families=families,
                choice_uniqueness="DISJOINT_NATIVE_POOLS" if families else "NOT_GUARANTEED",
                # This records parameter evidence, not proof of runtime slot interpretation.
                choice_layout_game_verified=False,
                reward_scope=audit_reward_scope(tables, active_pools),
                status="PARAMETER_EVIDENCE_ONLY_GAME_PENDING",
                limitations=["native selection/stacking/cleanup not newly verified",
                             "per-player dynamic weighting and mechanism dedup not implemented",
                             "three_choices_probe replaces two weapon reward slots for shared fort route"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--mode", choices=MODES, default="weighted")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if root / "local" not in output.parents:
        raise ValueError("Output must be inside project/local")
    manifest = compile_manifest(read_json(args.config or root / "data/phase1_native_buffs.json"),
                                load_tables(root), args.mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print("%s: %d guarded changes" % (manifest["experiment"], len(manifest["changes"])))


if __name__ == "__main__":
    main()
