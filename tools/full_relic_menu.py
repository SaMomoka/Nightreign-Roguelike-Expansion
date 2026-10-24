"""Compile a compact native ESD menu protocol for the full relic catalog."""
import itertools
import struct
from relic_selection import RelicSelection
from relic_filters import COLORS, EDITORS, groups, product_index

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
    color_labels={str(c):text("颜色："+zh,"Color: "+en) for c,zh,en in COLORS}
    page("select",[(text("普通遗物","Normal relic"),"editor0"),
                   (text("深夜遗物","Deep relic"),"editor2"),
                   (text("返回","Back"),"root")],"root")
    picker_audit=[]
    def paged(name,entries,back):
        chunks=[entries[i:i+6] for i in range(0,len(entries),6)] or [[]]
        for p,chunk in enumerate(chunks):
            choices=list(chunk)
            if p:choices.append((text(f"上一页（{p+1}/{len(chunks)}）",f"Previous ({p+1}/{len(chunks)})"),name+f"_p{p-1}"))
            if p+1<len(chunks):choices.append((text(f"下一页（{p+1}/{len(chunks)}）",f"Next ({p+1}/{len(chunks)})"),name+f"_p{p+1}"))
            choices.append((text("返回","Back"),back))
            page(name+f"_p{p}",choices,back)
        return name+"_p0"
    def label(names,count=None):
        zh=names['zhocn'];en=names.get('engus') or zh
        if count is not None:zh+=f"（{count}）";en+=f" ({count})"
        return text(zh,en)
    def picker(editor,slot,negative,back):
        base=f"editor{editor}"
        prefix=base+f"_slot{slot}"+("_negative" if negative else "_filter")
        categories=[]
        for cid,cat in sorted(groups(model,editor,negative).items()):
            submenus=[];total=0
            for sid,sub in sorted(cat['subcategories'].items()):
                families=[];count=0
                for fid,effects in sorted(sub['families'].items()):
                    variants=[]
                    for effect in effects:
                        e=model.entries[effect];target=prefix+f"_choose{effect}"
                        branches=[when(1,base),when(-1,base+"_error")]
                        if not negative and editor==2:branches.append(when(2,base+f"_slot{slot}_negative_p0"))
                        request(target,(300 if negative else 200)+editor*3+slot,effect,branches)
                        suffix="（需选负面）" if not negative and editor==2 and e['curse_requirement']=='required' else ""
                        variants.append((text(e['names']['zhocn'].strip()+suffix,(e['names'].get('engus') or e['names']['zhocn']).strip()+(" (choose drawback)" if suffix else "")),target))
                    subroute=prefix+f"_sub{sid}_p0"
                    target=variants[0][1] if len(variants)==1 else paged(prefix+f"_family{fid}",variants,subroute)
                    families.append((variants[0][0] if len(variants)==1 else label(model.entries[effects[0]]['names'],len(effects)),target))
                    count+=len(effects)
                target=paged(prefix+f"_sub{sid}",families,prefix+f"_cat{cid}_p0")
                submenus.append((label(sub['names'],count),target));total+=count
            target=paged(prefix+f"_cat{cid}",submenus,prefix+"_p0")
            names=cat['names'] if cid!=30 else {'zhocn':'通用','engus':'General'}
            categories.append((label(names,total),target))
        picker_audit.append(dict(editor=editor,slot=slot,negative=negative,effects=model.candidates(editor,negative)))
        return paged(prefix,categories,back)
    for editor in EDITORS:
        base=f"editor{editor}"
        node(base,template="clear",conditions=[go(base+"_query0")])
        for slot in range(3):
            query=base+f"_query{slot}"
            request(query,100+editor*3+slot,0,[when(TEXT_BASE,query+"_label",b"\x94"),when(-1,base+"_error")])
            node(query+"_label",entry=[add(slot+1,work(3))],conditions=[go(base+f"_query{slot+1}" if slot<2 else base+"_color_query")])
        request(base+"_color_query",700+editor,0,[when(TEXT_BASE,base+"_color_label",b"\x94"),when(-1,base+"_error")])
        node(base+"_color_label",entry=[add(4,work(3))],conditions=[go(base+"_finish")])
        node(base+"_finish",entry=[add(5,text("确定制作（1 暗痕）","Craft (1 Murk)")),add(6,text("返回","Back"))],conditions=[go(base+"_wait")])
        node(base+"_wait",template="show",conditions=[go(base+"_dispatch"),go("select")],modal=True)
        node(base+"_dispatch",conditions=[dict(eval=expression(integer(23)+b"\x84"+integer(i+1)+b"\x95"),target=target)
            for i,target in enumerate([base+f"_slot{s}_filter_p0" for s in range(3)]+[base+"_colors",base+"_craft","select"])]+[go("select")])
        colors=[]
        for c,zh,en in COLORS:
            target=base+f"_color{c}"
            request(target,600+editor,c,[when(1,base),when(-1,base+"_error")])
            colors.append((text(zh,en),target))
        page(base+"_colors",colors+[(text("返回","Back"),base)],base)
        page(base+"_error",[(text("选择未完成或词条冲突，请返回调整","Incomplete or conflicting selection; return to edit"),base)],base)
        request(base+"_craft",500+editor,0,[when(SHOP_BASE+product_index(editor,c),base+"_shop") for c,_,_ in COLORS]+[when(-1,base+"_error")])
        node(base+"_shop",template="dynamic_shop",conditions=[go(base)],modal=True)
        for slot in range(3):
            picker(editor,slot,False,base)
            if editor==2:
                cancel=base+f"_slot{slot}_cancel"
                request(cancel,400,0,[when(1,base),when(-1,base+"_error")])
                picker(editor,slot,True,cancel)
    ids={name:STATE_BASE+i for i,name in enumerate(states)}
    ids["exit"]=10
    for name,state in states.items():
        state["id"]=ids[name]
        for c in state["conditions"]:c["target"]=ids[c["target"]]
    return dict(schema_version=2,kind="full_relic_runtime_menu",markers=list(MARKERS),
        root_state=ids["root"],state_first=STATE_BASE,state_end=STATE_BASE+len(states),
        states=list(states.values()),texts=texts,labels=labels,color_labels=color_labels,
        visible_editors=list(EDITORS),picker_audit=picker_audit,shop_ids=[SHOP_BASE+i for i in range(8)],
        relic_ids=[9000000+i for i in range(8)],runtime_verified=False)
