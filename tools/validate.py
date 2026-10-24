"""NRE design-data validation. Does not claim engine or multiplayer support."""
import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))

def cycle(graph):
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            return True
        if node in done:
            return False
        visiting.add(node)
        if any(visit(n) for n in graph.get(node, [])):
            return True
        visiting.remove(node)
        done.add(node)
        return False
    return any(visit(n) for n in graph)

def number(v, minimum=0):
    return type(v) in (int, float) and math.isfinite(v) and v >= minimum

def validate(catalog, rules, mappings, release=False):
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    check(catalog.get("schema_version")==1, "unsupported catalog schema")
    buffs = catalog.get("buffs", [])
    check(isinstance(buffs,list) and bool(buffs), "buffs must be a nonempty list")
    if not isinstance(buffs,list) or any(not isinstance(b,dict) for b in buffs):
        return errors + ["invalid buff record"]
    ids = [b.get("id") for b in buffs]
    check(all(isinstance(i,str) and re.fullmatch(r"BUFF-\d{3}",i) for i in ids), "invalid buff ID")
    if not all(isinstance(i,str) for i in ids):
        return errors
    check(len(ids)==len(set(ids)), "duplicate buff ID")
    lookup = {b["id"]:b for b in buffs}
    required = {"name_zh","internal_name","categories","rarity","base_weight","prerequisites",
                "exclusions","repeatable","max_stacks","binding","trigger","parameters","tags",
                "required_buffs","owner","sync","game_dependencies","feasibility","game_test",
                "supported_versions","enabled","priority"}
    graph = {}
    for b in buffs:
        bid = b["id"]
        check(required <= b.keys(), f"{bid}: missing required fields")
        check(b.get("rarity") in {"common","rare","gold","red"}, f"{bid}: rarity")
        check(b.get("binding") in {"character","weapon","dual_future"}, f"{bid}: binding")
        check(number(b.get("base_weight")), f"{bid}: invalid weight")
        check(type(b.get("max_stacks")) is int and b["max_stacks"]>0, f"{bid}: stack cap")
        check(type(b.get("repeatable")) is bool and type(b.get("enabled")) is bool, f"{bid}: boolean flags")
        check(b.get("repeatable") or b.get("max_stacks")==1, f"{bid}: unique buff stack cap")
        check(b.get("feasibility") in {"verified","precedent","theoretical","unavailable"}, f"{bid}: feasibility")
        check(b.get("game_test") in {"not_run","passed","failed"}, f"{bid}: game test status")
        deps = []
        for field in ("prerequisites","required_buffs","exclusions"):
            refs=b.get(field, [])
            check(isinstance(refs,list) and all(isinstance(x,str) for x in refs), f"{bid}: {field} list")
            if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs):
                continue
            for ref in refs:
                check(ref in lookup and ref!=bid, f"{bid}: bad reference {ref}")
            if field!="exclusions":
                deps.extend(refs)
        graph[bid]=deps
        exclusions=b.get("exclusions",[])
        if isinstance(exclusions,list):
            check(not set(deps).intersection(x for x in exclusions if isinstance(x,str)), f"{bid}: required and excluded")
        t=b.get("trigger",{})
        check(isinstance(t,dict), f"{bid}: trigger object")
        if isinstance(t,dict):
            check(number(t.get("cooldown_seconds")), f"{bid}: cooldown")
            check(t.get("duration_seconds") is None or number(t["duration_seconds"]), f"{bid}: duration")
            check(isinstance(t.get("event"),str) and bool(t["event"]), f"{bid}: trigger event")
            if b.get("enabled"):
                check(t.get("event")!="unmapped", f"{bid}: unmapped trigger")
        params=b.get("parameters",{})
        if bid=="BUFF-010" and isinstance(params,dict):
            n,m=params.get("consumed_n"),params.get("returned_m")
            check(type(n) is int and n>0 and type(m) is int and m>=0, "consumable invalid counts")
            if type(n) is int and type(m) is int:
                check(m<n or params.get("allow_infinite") is True, "consumable infinite loop")
    check(not cycle(graph), "prerequisite cycle")
    # Transitive prerequisites may also make a buff impossible to acquire.
    for bid in graph:
        pending=list(graph[bid]); seen=set()
        while pending:
            n=pending.pop()
            if n not in seen:
                seen.add(n); pending.extend(graph.get(n,[]))
        check(not any(x in seen for x in lookup[bid].get("exclusions",[]) if isinstance(x,str)),
              f"{bid}: excluded transitive prerequisite")
    weights=rules.get("rarity_weights",{})
    check(isinstance(weights,dict) and set(weights)=={"common","rare","gold","red"}, "rarity weights keys")
    if isinstance(weights,dict):
        check(all(number(v) for v in weights.values()) and
              sum(v for v in weights.values() if number(v))>0, "rarity weights invalid")
    for field in ("candidate_count","max_chain_depth","max_events_per_root"):
        check(type(rules.get(field)) is int and rules[field]>0, f"invalid {field}")
    triggers={}; synergy_ids=set()
    for s in rules.get("synergies",[]):
        sid=s.get("id")
        check(isinstance(sid,str) and sid not in synergy_ids, "duplicate/invalid synergy ID")
        synergy_ids.add(sid)
        refs=s.get("requires",[])+s.get("excludes",[])
        check(all(r in lookup for r in refs), f"{sid}: unknown buff reference")
        check(not set(s.get("requires",[])) & set(s.get("excludes",[])), f"{sid}: conflicting condition")
        check(s.get("overwrite") in {"reject","strongest","refresh_capped","add_capped"}, f"{sid}: overwrite")
        for f in ("max_stacks","per_root_limit","max_triggers_per_run"):
            check(type(s.get(f)) is int and s[f]>0, f"{sid}: invalid {f}")
        check(number(s.get("cooldown_seconds")), f"{sid}: invalid cooldown")
        check(type(s.get("priority")) is int, f"{sid}: invalid priority")
        a,z=s.get("trigger"),s.get("emits")
        check(isinstance(a,str) and bool(a) and isinstance(z,str) and bool(z), f"{sid}: invalid trigger chain")
        if isinstance(a,str) and isinstance(z,str):
            triggers.setdefault(a,[]).append(z)
    check(not cycle(triggers), "trigger chain cycle")
    if release:
        check(bool(mappings.get("app_version")) and bool(mappings.get("regulation_version")), "release: game version missing")
        check(bool(re.fullmatch(r"[0-9a-fA-F]{64}", mappings.get("regulation_sha256") or "")), "release: input hash missing")
        active=[b for b in buffs if b.get("enabled")]
        check(bool(active), "release: no enabled verified game effects")
        for b in active:
            check(b.get("game_test")=="passed" and b.get("feasibility")=="verified", f'{b["id"]}: not game verified')
            check(mappings.get("regulation_version") in b.get("supported_versions",[]), f'{b["id"]}: unsupported version')
            matches=[m for m in mappings.get("effects",[]) if m.get("buff_id")==b["id"]]
            check(len(matches)==1 and all(m.get("param") and type(m.get("row_id")) is int and
                  m.get("field") and m.get("evidence") for m in matches), f'{b["id"]}: mapping missing')
    return errors

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--release",action="store_true")
    args=p.parse_args()
    try:
        errors=validate(read(ROOT/"data/buffs.json"),read(ROOT/"data/rules.json"),
                        read(ROOT/"integration/mappings.json"),args.release)
    except (ValueError,TypeError,KeyError,OSError) as e:
        p.exit(2,f"Invalid input: {e}\n")
    for error in errors:
        print("ERROR:",error)
    if errors:
        p.exit(1)
    print("PASS: design data valid; game integration NOT verified.")
