"""Build private, acyclic native nested pools. IDs below are NRE allocations."""
from fractions import Fraction
from phase1_rewards import (compile_manifest, audit_choice_families, FAMILY_POOLS,
                            GUARD_FIELDS, unique, SOURCE)

BASE = 1900100000
RARE_POOLS = (4200301,4200302,4200303)
# These are verified native pairs, not a general ID+1 inference rule.
PAIRS = {8000000:8000001,8010000:8010001,8020000:8020001,
         8100000:8100001,8200000:8200001,8200500:8200501}


def probability_report(groups, root_ids):
    """Exact fractions for static nested pool paths, with missing/cyclic rejection."""
    visiting=set()
    cache={}
    def visit(pool):
        if pool in visiting:raise ValueError("Reward pool cycle")
        if pool in cache:return cache[pool]
        if pool not in groups:raise ValueError("Missing reward pool")
        rows=groups[pool]
        if not rows or any(type(r["weight"]) is not int or r["weight"]<0 for r in rows):
            raise ValueError("Invalid pool weights")
        total=sum(r["weight"] for r in rows)
        if total<=0:raise ValueError("Empty positive-weight pool")
        visiting.add(pool)
        result={}
        for row in rows:
            # Check even zero-weight nested edges so latent cycles cannot be enabled later.
            if row["category"]==7:
                child=visit(row["target"])
            elif row["category"]==1:
                child={row["target"]:Fraction(1)}
            else:raise ValueError("Unsupported reward category")
            for item,p in child.items():
                result[item]=result.get(item,Fraction())+Fraction(row["weight"],total)*p
        visiting.remove(pool)
        cache[pool]=result
        return result
    return {root:{str(item):{"numerator":p.numerator,"denominator":p.denominator,
                            "percent":float(p*100)}
                  for item,p in sorted(visit(root).items()) if p}
            for root in root_ids}


def compile_tiered(config,tables):
    # Reuse all six-effect source and eligibility validation without generating
    # any edits to the shared native pools in the final manifest.
    basis=compile_manifest(config,tables,"distinct_choices")
    common=basis["choice_families"]
    rare=audit_choice_families(tables,RARE_POOLS)
    rarity=config.get("rarity_weights",{"normal":75,"rare":25})
    if set(rarity)!={"normal","rare"} or any(type(v) is not int or not 0<=v<=65535 for v in rarity.values()):
        raise ValueError("Rarity weights must be integers in 0..65535")
    if not sum(rarity.values()):raise ValueError("At least one rarity must remain enabled")
    occupied={int(r["ID"]) for r in tables["ItemTableParam"]}
    reserved=set(range(BASE,BASE+9))
    if occupied & reserved:raise ValueError("NRE pool ID collision")
    if occupied and max(occupied)>=BASE:
        raise ValueError("NRE append-only allocation must follow original rows")
    template=[(i,r) for i,r in enumerate(tables["ItemTableParam"])
              if r["ID"]=="1200600" and r["itemCategory"]=="7" and r["itemId"]=="4200100"]
    if len(template)!=1:raise ValueError("Native nested-pool exemplar changed")
    template_ordinal,template_row=template[0]
    for key,value in {"quantity":"1","onlyForClass":"0","eventFlagId":"0"}.items():
        if template_row[key]!=value:raise ValueError("Conditional nested-pool exemplar")
    all_goods=set()
    all_effects=set()
    additions=[]
    groups={}
    families=[]
    entry_weights={b["goods_id"]:b["weight"] for b in config["buffs"]}
    entry_weights.update({PAIRS[k]:v for k,v in list(entry_weights.items())})
    for family_index,(normal_group,rare_group) in enumerate(zip(common,rare)):
        family_goods=set(normal_group["goods_ids"])|set(rare_group["goods_ids"])
        family_effects=set(normal_group["sp_effect_ids"])|set(rare_group["sp_effect_ids"])
        if all_goods & family_goods or all_effects & family_effects:
            raise ValueError("Cross-family overlap across rarity tiers")
        all_goods.update(family_goods);all_effects.update(family_effects)
        root_id=BASE+family_index*3
        groups[root_id]=[]
        for tier_index,(source_pool,tier_name) in enumerate(((FAMILY_POOLS[family_index],"normal"),
                                                           (RARE_POOLS[family_index],"rare"))):
            leaf_id=root_id+tier_index+1
            groups[leaf_id]=[]
            additions.append(dict(table="ItemTableParam",row_id=root_id,
                source_row_id=int(template_row["ID"]),source_ordinal=template_ordinal,
                guard={k:int(template_row[k]) for k in GUARD_FIELDS},
                overrides={"itemId":leaf_id,"chanceWeight":rarity[tier_name]}))
            groups[root_id].append(dict(category=7,target=leaf_id,weight=rarity[tier_name]))
            for ordinal,row in enumerate(tables["ItemTableParam"]):
                if int(row["ID"])!=source_pool:continue
                if int(row["chanceWeight"])<=0:
                    raise ValueError("Unreviewed dormant native family member")
                item=int(row["itemId"])
                weight=entry_weights.get(item,int(row["chanceWeight"]))
                additions.append(dict(table="ItemTableParam",row_id=leaf_id,
                    source_row_id=source_pool,source_ordinal=ordinal,
                    guard={k:int(row[k]) for k in GUARD_FIELDS},
                    overrides={"chanceWeight":weight}))
                groups[leaf_id].append(dict(category=1,target=item,weight=weight))
        families.append(dict(pool_id=root_id,goods_ids=sorted(family_goods),
                             sp_effect_ids=sorted(family_effects),native_members=len(family_goods),
                             normal_pool_id=root_id+1,rare_pool_id=root_id+2))
    additions.sort(key=lambda row:row["row_id"])
    changes=[dict(c) for c in basis["changes"] if c["table"]=="ItemLotParam_enemy"]
    for change in changes:
        change["after"]=BASE+(change["row_id"]-6000050)*3
    roots=[f["pool_id"] for f in families]
    distribution=probability_report(groups,roots)
    return dict(schema_version=2,source_sha256=SOURCE,regulation_internal_version="10350000",
        experiment="PHASE1-tiered_choices",changes=changes,additions=additions,
        allocated_pool_ids=sorted(reserved),native_buffs=basis["native_buffs"],
        choice_families=families,choice_uniqueness="DISJOINT_PRIVATE_NESTED_POOLS",
        choice_layout_game_verified=False,rarity_weights=rarity,probability_report=distribution,
        reward_scope={"before_patch":[], "fort_base_npcs":basis["reward_scope"]["fort_base_npcs"],
                      "scope":"NRE private pool allocation; original native pools unchanged"},
        original_pool_rows_unchanged=True,status="PARAMETER_EVIDENCE_ONLY_GAME_PENDING",
        limitations=["Native nested selection and three-choice rendering still need game validation",
                     "Probability fractions describe parameter weights, not measured in-game rates",
                     "No per-player dynamic weights, mechanism dedup, or stack-cap runtime adapter"])
