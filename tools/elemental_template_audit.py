"""Read locally exported NR parameters; never modify or ship game resources."""
import argparse,itertools,json
from pathlib import Path

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def audit(folder):
    tables={n:{x['id']:x['fields'] for x in load(folder/(n+'.json'))}
            for n in ('MixcraftMagicParam','Magic','Bullet','AtkParam_Pc','SpEffectParam')}
    recipes={};out=[]
    for rid,row in tables['MixcraftMagicParam'].items():
        if rid==0:continue
        key=tuple(row['element'+str(i)] for i in (1,2,3))
        if key in recipes:raise ValueError('Duplicate element recipe')
        magic=row['magicId']
        if magic not in tables['Magic']:raise ValueError('Missing cocktail spell')
        recipes[key]=magic
    if set(recipes)!=set(itertools.product(range(1,5),repeat=3)):
        raise ValueError('Expected all 64 native permutations')
    for key,magic in recipes.items():
        for perm in itertools.permutations(key):
            if recipes[perm]!=magic:raise ValueError('Order changes cocktail result')
    for magic in sorted(set(recipes.values())):
        row=tables['Magic'][magic];roots=[];unresolved=[]
        for i in range(1,11):
            category=row.get('refCategory'+str(i));rid=row.get('refId'+str(i),-1)
            if rid<0 or category not in (1,2):continue
            table='Bullet' if category==1 else 'SpEffectParam'
            if rid not in tables[table]:
                unresolved.append(dict(table=table,id=rid,slot=i));continue
            roots.append(dict(table=table,id=rid))
        todo=[x['id'] for x in roots if x['table']=='Bullet'];visited=set();attacks=set();effects=set()
        while todo:
            rid=todo.pop()
            if rid in visited:continue
            visited.add(rid);b=tables['Bullet'][rid]
            for k in ('HitBulletID','intervalCreateBulletId'):
                link=b.get(k,-1)
                if link>=0:
                    if link not in tables['Bullet']:raise ValueError('Missing child bullet')
                    todo.append(link)
            attack=b['atkId_Bullet']
            if attack>=0:
                if attack not in tables['AtkParam_Pc']:raise ValueError('Missing player attack')
                attacks.add(attack)
            effects.update(v for k,v in b.items() if k.startswith('spEffectId') and v>0)
        if not effects<=tables['SpEffectParam'].keys():raise ValueError('Missing bullet effect')
        out.append(dict(magic_id=magic,recipes=[list(k) for k,v in recipes.items() if v==magic],roots=roots,unresolved_roots=unresolved,
                        bullet_ids=sorted(visited),attack_ids=sorted(attacks),hit_effect_ids=sorted(effects)))
    return dict(status='PARAMETER_REFERENCE_GRAPH_ONLY',source=load(folder/'sources.json'),
                element_codes={'1':'magic','2':'fire','3':'lightning','4':'holy'},
                ordered_combinations=len(recipes),spell_count=len(out),spells=out,
                native_enemy_residue_storage=None,native_hit_owner_api=None,
                native_weapon_instance_binding=None,game_verified=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(a.folder);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: 64 ordered recipes, '+str(result['spell_count'])+' spell graphs; engine behavior unverified')
