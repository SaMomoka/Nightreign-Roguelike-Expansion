"""Compile a compact native ESD menu protocol for the full relic catalog."""
import itertools
import struct
from relic_selection import RelicSelection

MAGIC = 1599843857
MARKERS = tuple(MAGIC+i for i in range(4))
TEXT_BASE = 1900400000
STATE_BASE = 400000
SHOP_BASE = 1900200000


def integer(n):
    return b"\x82"+struct.pack("<i",n)


def work(index):
    if index not in range(4):
        raise ValueError("Only native work values 0–3 exist")
    return integer(100)+integer(index)+b"\x85"


def expression(raw):
    return (raw+b"\xa1").hex()


def set_work(index,value):
    if index not in range(4):
        raise ValueError("Invalid native work value index")
    return dict(bank=1,id=100,args=[expression(integer(index)),expression(integer(value))])


def compile_menu(catalog):
    model=RelicSelection(catalog)
    texts=[];text_lookup={}
    def text(zh,en=None):
        pair=(zh,en or zh)
        if pair not in text_lookup:
            text_lookup[pair]=TEXT_BASE+len(texts)
            texts.append(dict(id=text_lookup[pair],zhocn=pair[0],engus=pair[1]))
        return text_lookup[pair]
    # Each slot label represents an atomic positive/negative bundle, rather
    # than the Cartesian product of three separate slots.
    labels={}
    for kind,editor in (("normal",0),("deep",2)):
        for slot in range(3):
            labels[f"{kind}:{slot}:0:0"]=text(f"词条 {slot+1}：未选择",f"Effect {slot+1}: Not selected")
            for positive in model.candidates(editor):
                e=model.entries[positive]
                curses=model.candidates(2,True) if kind=="deep" and e["curse_requirement"]=="required" else [None]
                for curse in curses:
                    zh=e["names"]["zhocn"].strip();en=e["names"].get("engus",zh).strip()
                    if curse:
                        c=model.entries[curse]
                        zh+=" / "+c["names"]["zhocn"].strip()
                        en+=" / "+c["names"].get("engus",c["names"]["zhocn"]).strip()
                    labels[f"{kind}:{slot}:{positive}:{curse or 0}"]=text(f"词条 {slot+1}：{zh}",f"Effect {slot+1}: {en}")
    states={}
    def node(name,entry=None,conditions=None,template=None,modal=False):
        if name in states:raise ValueError("Duplicate state")
        states[name]=dict(name=name,entry=entry or [],conditions=conditions or [],template=template,modal=modal)
        return name
    def go(target):
        return dict(eval="41a1",target=target)
    def when(value,target,comparison=b"\x95"):
        return dict(eval=expression(work(3)+integer(value)+comparison),target=target)
    def add(choice,label):
        value=integer(label) if isinstance(label,int) else label
        return dict(bank=1,id=149,args=[expression(integer(choice)),expression(value),
                    expression(integer(-1)),expression(integer(choice)),expression(integer(0))])
    def page(name,entries,back):
        node(name,template="clear",conditions=[go(name+"_items")])
        node(name+"_items",entry=[add(i+1,label) for i,(label,target) in enumerate(entries)],
             conditions=[go(name+"_wait")])
        node(name+"_wait",template="show",conditions=[go(name+"_dispatch"),go(back)],modal=True)
        node(name+"_dispatch",conditions=[
            dict(eval=expression(integer(23)+b"\x84"+integer(i+1)+b"\x95"),target=target)
            for i,(label,target) in enumerate(entries)]+[go(back)])
    def request(name,operation,payload,branches):
        node(name,entry=[set_work(1,0),set_work(3,0),set_work(2,payload),set_work(1,operation)],
             conditions=[go(name+"_response")])
        node(name+"_response",conditions=branches,modal=True)
    page("root",[(text("原商店","Original shop"),"original_shop"),
                 (text("NRE 遗物制作","NRE relic crafting"),"connect"),
                 (text("离开","Leave"),"exit")],"exit")
    node("original_shop",template="original_shop",conditions=[go("root")],modal=True)
    node("connect",entry=[set_work(i,value) for i,value in enumerate(MARKERS)],conditions=[go("connected")])
    node("connected",conditions=[when(1,"select")],modal=True)
    page("select",[(text(("普通" if e<2 else "深夜")+f"遗物 {e%2+1}",
                        ("Normal" if e<2 else "Deep")+f" relic {e%2+1}"),f"editor{e}") for e in range(4)]+
                 [(text("返回","Back"),"root")],"root")
    for editor in range(4):
        base=f"editor{editor}"
        node(base,template="clear",conditions=[go(base+"_query0")])
        for slot in range(3):
            query=base+f"_query{slot}"
            request(query,100+editor*3+slot,0,[when(TEXT_BASE,query+"_label",b"\x94"),when(-1,base+"_error")])
            node(query+"_label",entry=[add(slot+1,work(3))],
                 conditions=[go(base+f"_query{slot+1}" if slot<2 else base+"_finish")])
        node(base+"_finish",entry=[add(4,text("确定制作（1 暗痕）","Craft (1 Murk)")),
                                  add(5,text("返回","Back"))],conditions=[go(base+"_wait")])
        node(base+"_wait",template="show",conditions=[go(base+"_dispatch"),go("select")],modal=True)
        node(base+"_dispatch",conditions=[
            dict(eval=expression(integer(23)+b"\x84"+integer(i+1)+b"\x95"),target=target)
            for i,target in enumerate([base+f"_slot{s}_page0" for s in range(3)]+[base+"_craft","select"])]
             +[go("select")])
        page(base+"_error",[(text("选择未完成或词条冲突，请返回调整",
                                  "Incomplete or conflicting selection; return to edit"),base)],base)
        request(base+"_craft",500+editor,0,[when(SHOP_BASE+editor,base+"_shop"),when(-1,base+"_error")])
        node(base+"_shop",template="dynamic_shop",conditions=[go(base)],modal=True)
        for slot in range(3):
            prefix=base+f"_slot{slot}"
            first=model.page(editor)
            for p in range(first["pages"]):
                source=model.page(editor,p)
                entries=[]
                for choice in source["choices"]:
                    effect=choice["effect_id"];e=model.entries[effect]
                    target=prefix+f"_choose{effect}"
                    branches=[when(1,base),when(-1,base+"_error")]
                    if editor>=2:branches.append(when(2,prefix+"_negative0"))
                    request(target,200+editor*3+slot,effect,branches)
                    suffix="（需选负面）" if editor>=2 and e["curse_requirement"]=="required" else ""
                    entries.append((text(e["names"]["zhocn"].strip()+suffix,
                                         e["names"].get("engus",e["names"]["zhocn"]).strip()+
                                         (" (choose drawback)" if suffix else "")),target))
                if source["previous"] is not None:entries.append((text("上一页","Previous page"),prefix+f"_page{p-1}"))
                if source["next"] is not None:entries.append((text("下一页","Next page"),prefix+f"_page{p+1}"))
                entries.append((text("返回","Back"),base))
                page(prefix+f"_page{p}",entries,base)
            if editor<2:continue
            request(prefix+"_cancel",400,0,[when(1,base),when(-1,base+"_error")])
            first=model.page(editor,negative=True)
            for p in range(first["pages"]):
                source=model.page(editor,p,True);entries=[]
                for choice in source["choices"]:
                    curse=choice["effect_id"];e=model.entries[curse]
                    target=prefix+f"_curse{curse}"
                    request(target,300+editor*3+slot,curse,[when(1,base),when(-1,base+"_error")])
                    entries.append((text(e["names"]["zhocn"].strip(),e["names"].get("engus",e["names"]["zhocn"]).strip()),target))
                if p:entries.append((text("上一页","Previous page"),prefix+f"_negative{p-1}"))
                if p+1<source["pages"]:entries.append((text("下一页","Next page"),prefix+f"_negative{p+1}"))
                entries.append((text("取消，保留原词条","Cancel; keep previous effect"),prefix+"_cancel"))
                page(prefix+f"_negative{p}",entries,prefix+"_cancel")
    ids={name:STATE_BASE+i for i,name in enumerate(states)}
    ids["exit"]=10
    for name,state in states.items():
        state["id"]=ids[name]
        for c in state["conditions"]:c["target"]=ids[c["target"]]
    return dict(schema_version=1,kind="full_relic_runtime_menu",markers=list(MARKERS),
        root_state=ids["root"],state_first=STATE_BASE,state_end=STATE_BASE+len(states),
        states=list(states.values()),texts=texts,labels=labels,shop_ids=[SHOP_BASE+i for i in range(4)],
        relic_ids=[9000000+i for i in range(4)],runtime_verified=False)
