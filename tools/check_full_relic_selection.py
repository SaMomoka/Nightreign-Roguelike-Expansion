"""Exercise every reconciled candidate; never launch or modify the game."""
import argparse
import json
from pathlib import Path

from relic_presets import ROOT, load
from relic_selection import RelicSelection, menu_blueprint


def check(root=ROOT):
    root=Path(root)
    catalog=load(root/"local/evidence/relic-full-catalog.json")
    model=RelicSelection(catalog)
    counts={}
    for editor in (0,2):
        values=model.candidates(editor)
        for effect in values:
            route=model.choose_positive(editor,0,effect)
            if route=="choose_negative":
                model.choose_negative(model.candidates(editor,True)[0])
            bundle=model.drafts[editor][0]
            assert bundle["effect_id"]==effect
            assert (bundle["curse_id"] is not None)==(editor==2 and model.entries[effect]["curse_requirement"]=="required")
        counts["normal" if editor==0 else "deep"]=len(values)
    required=[e for e in model.candidates(2) if model.entries[e]["curse_requirement"]=="required"]
    pairs=0
    for effect in required:
        for curse in model.candidates(2,True):
            model.choose_positive(2,0,effect);model.choose_negative(curse)
            assert model.drafts[2][0]==dict(effect_id=effect,curse_id=curse)
            pairs+=1
    blueprint=menu_blueprint(catalog)
    for picker in blueprint["pickers"]:
        ids=[choice["effect_id"] for page in picker["pages"] for choice in page["choices"]]
        assert ids==model.candidates(picker["editor"],picker["negative"])
        assert len(ids)==len(set(ids))
    (root/"local/evidence/relic-full-menu-blueprint.json").write_text(
        json.dumps(blueprint,ensure_ascii=False,indent=2),encoding="utf-8")
    report=dict(status="PASS_CATALOG_AND_SELECTION_RUNTIME_UNBOUND",
        normal_candidates=counts["normal"],deep_candidates=counts["deep"],
        deep_requires_negative=len(required),deep_no_negative=counts["deep"]-len(required),
        negative_candidates=len(model.candidates(2,True)),positive_negative_pairs_checked=pairs,
        picker_pages=sum(len(p["pages"]) for p in blueprint["pickers"]),
        source_sha256=catalog["source_sha256"],workbook_sha256=catalog["reference"]["sha256"],
        workbook_rule_discrepancies=catalog["discrepancies"],
        game_verified=False,game_launched=False,runtime_adapter=None,
        installed_test_package_unchanged=True)
    (root/"tests/ingame/RELIC-FULL-CATALOG.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args()
    report=check(args.root)
    print(json.dumps({k:v for k,v in report.items() if k!="workbook_rule_discrepancies"},ensure_ascii=False,indent=2))
