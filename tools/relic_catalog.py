"""Read-only NR CSV importer. Pool row IDs are intentionally non-unique.

Exports evidence and draft candidates, never game files or save changes.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

PINNED_SHA256 = "876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268"
TABLES = ("EquipParamAntique", "AttachEffectTableParam", "AttachEffectParam",
          "AntiqueStandParam", "SpEffectParam")
SLOTS = [f"attachEffectTableId_{i}" for i in range(1, 4)]
CURSES = [f"attachEffectTableId_curse{i}" for i in range(1, 4)]
REFS = ["onHitSpEffect", "passiveSpEffectId_1", "passiveSpEffectId_2",
        "passiveSpEffectId_3", "permanentSpEffectId"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def read_table(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: missing required columns")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"{path}: malformed CSV")
    return rows


def unique_index(rows):
    result = {}
    for row in rows:
        key = int(row["ID"])
        if key in result:
            raise ValueError(f"Duplicate ID outside pool table: {key}")
        result[key] = row
    return result


def build_catalog(source, regulation):
    if digest(regulation) != PINNED_SHA256:
        raise ValueError("Regulation hash mismatch; re-audit version before importing")
    source = Path(source)
    required = {
        "EquipParamAntique": ["ID", "Name", "isDeepRelic", "relicColor", *SLOTS, *CURSES],
        "AttachEffectTableParam": ["ID", "attachEffectId", "chanceWeight", "chanceWeight_dlc"],
        "AttachEffectParam": ["ID", "Name", "compatibilityId", "exclusivityId", "isDebuff", *REFS],
        "AntiqueStandParam": ["ID", "heroType", "relicSlot1", "deepRelicSlot1"],
        "SpEffectParam": ["ID"],
    }
    rows = {name: read_table(source / (name + ".csv"), required[name]) for name in TABLES}
    # SpEffect values stay in private CSV files; only reference IDs are needed here.
    effects = unique_index(rows["AttachEffectParam"])
    sp_ids = set(unique_index(rows["SpEffectParam"]))
    antiques = unique_index(rows["EquipParamAntique"])
    stands = unique_index(rows["AntiqueStandParam"])
    pools = defaultdict(list)
    missing_effects, missing_pools, missing_speffects = [], [], []
    for ordinal, row in enumerate(rows["AttachEffectTableParam"]):
        pool_id, effect_id = int(row["ID"]), int(row["attachEffectId"])
        pools[pool_id].append({
            "source_ordinal": ordinal, "effect_id": effect_id,
            "weight": int(row["chanceWeight"]), "dlc_weight_raw": int(row["chanceWeight_dlc"]),
        })
        if effect_id >= 0 and effect_id not in effects:
            missing_effects.append({"pool_id": pool_id, "ordinal": ordinal, "effect_id": effect_id})
    for key, row in effects.items():
        for field in REFS:
            target = int(row[field])
            if target >= 0 and target not in sp_ids:
                missing_speffects.append({"effect_id": key, "field": field, "target": target})
    templates = []
    for key, row in antiques.items():
        links = {field: int(row[field]) for field in SLOTS + CURSES}
        for field, target in links.items():
            if target >= 0 and target not in pools:
                missing_pools.append({"antique_id": key, "field": field, "pool_id": target})
        templates.append({
            "id": key, "name": row["Name"], "deep_raw": int(row["isDeepRelic"]),
            "color_raw": int(row["relicColor"]), "pool_links": links,
            # Not a declaration that this template is obtainable/equippable.
            "game_legal_verified": False,
        })
    summary = {
        "counts": {name: len(value) for name, value in rows.items()},
        "pool_groups": len(pools),
        "pool_groups_with_repeated_id": sum(len(v) > 1 for v in pools.values()),
        "deep_raw_counts": dict(Counter(r["isDeepRelic"] for r in antiques.values())),
        "missing_pool_references": missing_pools,
        "missing_effect_references": missing_effects,
        "missing_speffect_references": missing_speffects,
    }
    catalog = {
        "schema_version": 1, "regulation_sha256": PINNED_SHA256,
        "regulation_version": "1.03.5", "game_legal_verified": False,
        "csv_sha256": {name: digest(source / (name + ".csv")) for name in TABLES},
        "provenance_note": "CSV exports must come from the pinned input; hash pin alone does not authenticate CSV contents.",
        "summary": summary, "templates": templates, "pools": dict(pools),
        "effects": list(effects.values()), "stands": list(stands.values()),
    }
    return catalog


def inspect_template(catalog, template_id):
    template = next((r for r in catalog["templates"] if r["id"] == template_id), None)
    if template is None:
        raise ValueError("Unknown template ID")
    slots = []
    for field, pool_id in template["pool_links"].items():
        if pool_id < 0:
            continue
        entries = catalog["pools"].get(str(pool_id), catalog["pools"].get(pool_id))
        if entries is None:
            raise ValueError(f"Unresolved pool {pool_id}")
        # Keep base and DLC views separate. Do not interpret -1 as fallback without evidence.
        slots.append({"field": field, "pool_id": pool_id, "candidate_rows": len(entries),
                      "base_positive_weight_effects": sorted(set(
                          r["effect_id"] for r in entries if r["weight"] > 0 and r["effect_id"] >= 0)),
                      "dlc_weight_semantics": "UNVERIFIED"})
    return {"template": template, "slots": slots, "status": "draft_not_applicable",
            "unresolved": ["pool selection semantics", "compatibility/exclusivity semantics",
                           "obtainability and save persistence", "per-player application"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("import")
    load.add_argument("--csv-dir", type=Path, required=True)
    load.add_argument("--regulation", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--catalog", type=Path, required=True)
    inspect.add_argument("--template-id", type=int, required=True)
    args = parser.parse_args()
    if args.command == "import":
        result = build_catalog(args.csv_dir, args.regulation)
        # No overwrite of existing evidence.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        compact = {key: len(value) if isinstance(value, list) else value
                   for key, value in result["summary"].items()}
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    else:
        result = inspect_template(json.loads(args.catalog.read_text(encoding="utf-8-sig")), args.template_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
