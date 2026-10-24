"""Audit the built two-kind/color/filter menu without claiming game acceptance."""
import argparse
import json
from pathlib import Path
from relic_presets import ROOT,load
from relic_launch import verify_package
from relic_filters import EDITORS,groups,product_index
from relic_selection import RelicSelection


def check(root=ROOT):
    root=Path(root);folder=Path(load(root/'local/full-relic-package.json')['path'])
    verify_package(folder,root)
    plan=load(folder/'full-menu-plan.json');catalog=load(folder/'runtime-catalog.json')
    model=RelicSelection(catalog);layout=load(folder/'runtime-layout.json')
    assert plan['schema_version']==2 and plan['visible_editors']==[0,2]
    by_id={r['id']:r for r in layout['rows']}
    assert set(by_id)==set(range(9000000,9000008))
    products=[]
    for p in plan['initial_products']:
        raw=bytes.fromhex(by_id[p['id']]['initial_hex'])
        assert p['id']==9000000+product_index(p['editor'],p['color'])
        assert p['shop_id']==1900200000+product_index(p['editor'],p['color'])
        assert raw[4]==p['color'] and (raw[7]&1)==(p['editor']==2)
        products.append(dict(editor=p['editor'],color=p['color'],relic_id=p['id'],shop_id=p['shop_id'],template_id=p['template_id']))
    coverage=[]
    for editor,negative in ((0,False),(2,False),(2,True)):
        tree=groups(model,editor,negative)
        families=[v for cat in tree.values() for sub in cat['subcategories'].values() for v in sub['families'].values()]
        ids=[i for family in families for i in family]
        assert sorted(ids)==model.candidates(editor,negative) and len(ids)==len(set(ids))
        coverage.append(dict(editor=editor,negative=negative,effects=len(ids),categories=len(tree),
            subcategories=sum(len(c['subcategories']) for c in tree.values()),families=len(families),
            largest_family=max(map(len,families)),unclassified=sum(len(v) for s in tree.get(-1,{}).get('subcategories',{}).values() for v in s['families'].values())))
    assert len(plan['picker_audit'])==9
    assert all(a['effects']==model.candidates(a['editor'],a['negative']) for a in plan['picker_audit'])
    report=dict(schema_version=1,status='BUILD_AND_DATA_PASS_GAME_TEST_PENDING',package=folder.name,
        entry_labels=['普通遗物','深夜遗物'],editor_actions=6,colors=['红色','蓝色','黄色','绿色'],products=products,
        filter_coverage=coverage,states=len(plan['states']),texts=len(plan['texts']),native_filter_panel_reused=False,
        native_filter_data_reused=True,native_payment=True,price_murk=1,game_verified=False,
        limitations=['Native dialog hierarchy, not the Ritual grid/filter panel.',
                     'Colors, purchases, repeated recipes and restart persistence require in-game confirmation.',
                     'New package uses a fresh isolated save; do not load prior experimental custom items.'])
    (root/'tests/ingame/RELIC-FILTER-COLOR-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT)
    print(json.dumps(check(p.parse_args().root),ensure_ascii=False,indent=2))
