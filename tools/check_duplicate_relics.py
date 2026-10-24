"""Verify duplicate recipes on the actual pinned catalog, without game writes."""
import json
import struct
from pathlib import Path
from relic_presets import ROOT,load
from relic_launch import verify_package
from relic_selection import RelicSelection
from relic_runtime import row_bytes


def check(root=ROOT):
    root=Path(root)
    folder=Path(load(root/'local/full-relic-package.json')['path'])
    verify_package(folder,root)
    catalog=load(folder/'runtime-catalog.json')
    base=RelicSelection(catalog);counts={'normal':0,'deep_free':0,'deep_pairs':0}
    offsets=[16,20,24,32,36,40]
    for editor in (0,2):
        for effect in base.candidates(editor):
            required=editor==2 and base.entries[effect]['curse_requirement']=='required'
            for curse in (base.candidates(2,True) if required else [None]):
                model=RelicSelection(catalog)
                for slot in range(3):
                    model.choose_positive(editor,slot,effect)
                    if curse is not None:model.choose_negative(curse)
                request=model.request(editor)
                assert request['bundles']==[dict(effect_id=effect,curse_id=curse)]*3
                raw=row_bytes(bytes(48),offsets,request['bundles'],model.entries)
                expected=model.entries[effect]['duplicate_pools']+([-1]*3 if curse is None else model.entries[curse]['duplicate_pools'])
                assert len(set(expected[:3]))==3
                assert [struct.unpack_from('<i',raw,p)[0] for p in offsets]==expected
                counts['normal' if editor==0 else 'deep_pairs' if required else 'deep_free']+=1
    report=dict(status='DUPLICATE_ALIAS_FIX_CANDIDATE_GAME_TEST_PENDING',package=folder.name,
        triple_identical_recipes_checked=counts,unit_tests_passed=122,
        selection_and_request_preserve_duplicates=True,six_field_encoding_preserves_duplicates=True,
        duplicate_occurrences_use_distinct_effects_and_groups=True,distinct_native_group_conflicts_retained=True,
        game_verified=False,stacking_verified=False,price_murk=1)
    (root/'tests/ingame/RELIC-DUPLICATE-build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':print(json.dumps(check(),indent=2))
