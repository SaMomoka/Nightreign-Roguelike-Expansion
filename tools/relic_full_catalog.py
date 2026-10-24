"""Reconcile a user reference workbook with pinned local Nightreign relic data.

The workbook is read as data only. Native membership determines availability;
weapon/buff rows and textual notes never become executable instructions.
"""
import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from relic_presets import ROOT, CHARACTERS, Planner, load
from phase1_rewards import SOURCE

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
SHEETS = ("局外词条（遗物+武器固有效果）", "深夜模式局外词条（遗物+武器固有效果）")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def workbook_rows(path):
    """Read cached scalar values, never execute formulas/macros/external links."""
    output, inventory = [], []
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(e.itertext()) for e in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships}
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in book.find("m:sheets", NS):
            title = sheet.attrib["name"]
            inventory.append(title)
            if title not in SHEETS:
                continue
            target = targets[sheet.attrib[REL]].replace("\\", "/")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            for row in ET.fromstring(archive.read(target)).findall(".//m:sheetData/m:row", NS):
                values = {}
                for cell in row:
                    address = cell.attrib["r"]
                    column = re.sub(r"\d+$", "", address)
                    node = cell.find("m:v", NS)
                    value = node.text if node is not None else ""
                    if cell.attrib.get("t") == "s" and value:
                        value = strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        inline = cell.find("m:is", NS)
                        value = "".join(inline.itertext()) if inline is not None else ""
                    values[column] = value or ""
                raw_id = values.get("A", "").strip()
                if not re.fullmatch(r"\d+", raw_id):
                    continue
                output.append(dict(sheet=title, row=int(row.attrib["r"]), effect_id=int(raw_id),
                                   cells=values))
    if not set(SHEETS).issubset(inventory):
        raise ValueError("Reference workbook is missing the expected relic sheets")
    return output, inventory


def active(row):
    # Preserve the existing pinned planner's base/DLC policy.
    return row["weight"] > 0 and (row["dlc_weight_raw"] == -1 or row["dlc_weight_raw"] > 0)


def compile_catalog(native, budgets, texts, reference):
    if native["regulation_sha256"] != SOURCE:
        raise ValueError("Unreviewed game version")
    planner = Planner(native, budgets)
    effects = planner.effects
    refs = defaultdict(list)
    for r in reference:
        refs[r["effect_id"]].append(r)
    provenance = defaultdict(list)
    named_provenance = defaultdict(list)
    for template in native["templates"]:
        for field, pool_id in template["pool_links"].items():
            if pool_id < 0:
                continue
            kind = "deep" if template["deep_raw"] == 1 else "normal"
            for row in native["pools"].get(str(pool_id), []):
                effect_id = row["effect_id"]
                if effect_id in effects and active(row):
                    link = dict(template_id=template["id"], kind=kind, field=field,
                                pool_id=pool_id, source_ordinal=row["source_ordinal"])
                    provenance[effect_id].append(link)
                    if texts["languages"]["zhocn"]["antique"].get(str(template["id"]), "").strip():
                        named_provenance[effect_id].append(link)
    candidates, excluded, discrepancies = [], [], []
    for effect_id in sorted(set(refs) | set(provenance)):
        effect = effects.get(effect_id)
        links = provenance.get(effect_id, [])
        if effect is None or not links:
            excluded.append(dict(effect_id=effect_id,
                reason="not_in_attach_effect_param" if effect is None else "no_active_relic_template_reference",
                references=refs.get(effect_id, [])))
            continue
        debuff = effect["isDebuff"] == "1"
        modes = sorted({p["kind"] for p in links if ("curse" in p["field"]) == debuff})
        selectable_modes = sorted({p["kind"] for p in named_provenance.get(effect_id, [])
                                   if ("curse" in p["field"]) == debuff})
        if not modes:
            excluded.append(dict(effect_id=effect_id, reason="polarity_mismatch", references=refs.get(effect_id, [])))
            continue
        if debuff:
            requirement = "negative"
        elif effect_id in planner.curse_required and effect_id in planner.curse_free:
            requirement = "ambiguous"
        elif effect_id in planner.curse_required:
            requirement = "required"
        elif effect_id in planner.curse_free:
            requirement = "none"
        else:
            requirement = "not_in_deep_random_pools"
        native_names, native_info = {}, {}
        text_id = str(effect["attachTextId"])
        for language, tables in texts["languages"].items():
            native_names[language] = tables["name"].get(text_id, "")
            native_info[language] = tables["info"].get(text_id, "")
        labels = [r["cells"].get("B", "") for r in refs.get(effect_id, [])]
        for r in refs.get(effect_id, []):
            if r["sheet"] == SHEETS[1] and not debuff:
                raw = r["cells"].get("F", "").strip()
                expected = {"是": "required", "否": "none", "有": "required", "无": "none",
                            "附带负面词条": "required", "不附带负面词条": "none"}.get(raw)
                if expected and requirement != expected:
                    discrepancies.append(dict(effect_id=effect_id, field="curse_required",
                        workbook=raw, native=requirement, sheet=r["sheet"], cell="F"+str(r["row"])))
        candidates.append(dict(effect_id=effect_id, modes=modes, selectable_modes=selectable_modes, is_negative=debuff,
            curse_requirement=requirement, deterministic_pool=planner.fixed_pools.get(effect_id),
            native_text_id=int(text_id), names=native_names, info=native_info,
            reference_labels=labels, references=refs.get(effect_id, []),
            allowed_characters=[c for c in CHARACTERS if effect.get("allow"+c) == "1"],
            compatibility_id=int(effect["compatibilityId"]), exclusivity_id=int(effect["exclusivityId"]),
            order=int(effect["overrideBaseEffectId"]), native_modifier=effect["displayedModifierValue"],
            normal_random=effect_id in planner.normal, deep_random=effect_id in planner.deep,
            curse_random=effect_id in planner.curses, native_links=links,
            game_verified=False))
    counts = Counter()
    for c in candidates:
        for mode in c["selectable_modes"]:
            counts[mode + ("_negative" if c["is_negative"] else "_positive")] += 1
        if c["deep_random"]:
            counts["deep_" + c["curse_requirement"]] += 1
        if not c["names"].get("zhocn"):
            counts["missing_native_chinese"] += 1
    return dict(schema_version=1, source_sha256=SOURCE, status="CATALOG_RECONCILED_RUNTIME_PENDING",
        counts=dict(counts), entries=candidates, excluded=excluded, discrepancies=discrepancies,
        coverage=dict(workbook_rows=len(reference), referenced_unique_effects=len(refs),
                      candidate_effects=len(candidates), excluded_effects=len(excluded)),
        boundaries=["Native template references establish data presence, not obtainability.",
                    "Reference descriptions are not executed or treated as game APIs.",
                    "Character restrictions are retained as labels and constraints.",
                    "Runtime crafting for this full catalog is not implemented by this importer."])


def build(root, workbook):
    root, workbook = Path(root), Path(workbook)
    native = load(root / "local/evidence/relic-catalog.json")
    verification = load(root / "local/evidence/relic-export-verification.json")
    if verification["status"] != "PASS" or verification["regulation_sha256"] != SOURCE:
        raise ValueError("Native exports are not verified")
    for name, expected in native["csv_sha256"].items():
        if digest(root / "local/evidence" / (name + ".csv")) != expected:
            raise ValueError("Native source CSV changed: " + name)
    texts = load(root / "local/evidence/relic-text.json")
    for source in texts["sources"]:
        if digest(root / "local/native-menu/original" / source["path"]) != source["sha256"]:
            raise ValueError("Original text resource changed")
    refs, sheets = workbook_rows(workbook)
    result = compile_catalog(native, load(root / "data/relic_budgets.json"), texts, refs)
    result["reference"] = dict(path=str(workbook), sha256=digest(workbook), sheets=sheets)
    destination = root / "local/evidence/relic-full-catalog.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workbook", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.root, args.workbook)
    print(json.dumps({k: result[k] for k in ("status", "counts", "coverage", "discrepancies")}, ensure_ascii=False, indent=2))
