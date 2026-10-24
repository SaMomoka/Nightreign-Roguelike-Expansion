"""Native training reward selector, using the audited merchant dialog primitives."""
import struct
from full_relic_menu import integer, expression
from numeric_reward import TOKEN_GOODS,TOKEN_EFFECT,READY_FLAG,extra_entries,redemption_events

MAGIC=1599848000
MARKERS=tuple(MAGIC+i for i in range(4))
FLAG=10009880
STATE_BASE=600000
TEXT_BASE=1900600000
POOL_IDS=(1900610000,1900610001,1900610002)

def catalog(native, full_native=None):
    result=[]
    rates=(1.05,1.05,1.05,1.03,0.96,0.96)
    names=('生命上限 +5%','FP 上限 +5%','精力上限 +5%','物理攻击 +3%','物理承伤 -4%','属性承伤 -4%')
    for i,b in enumerate(native['buffs']):
        result.append(dict(index=i,name='NRE '+names[i],goods_id=8900000+i,category="NRE 数值实验",
            source_goods=b['goods_id'],source_permanent=b['permanent_buff_id'],source_effect=b['sp_effect_id'],
            fields={k:rates[i] for k in b['effect_fields']},numeric_value=(5,5,5,3,4,4)[i],custom=True))
    if full_native is not None:
        result.extend(extra_entries(len(result)))
        result.append(dict(index=len(result),goods_id=TOKEN_GOODS,name='数值强化（领取后任选一项）',category='数值强化入口',custom=False,token=True))
    for b in (full_native if full_native is not None else native['buffs']):
        result.append(dict(b,index=len(result),name=b['name'],goods_id=b['goods_id'],custom=False,category=b.get('category','原生对照')))
    return result

def compile_menu(entries):
    if not entries or [e['index'] for e in entries]!=list(range(len(entries))):
        raise ValueError('Invalid candidate indexes')
    if len({e['goods_id'] for e in entries})!=len(entries) or any(not 0<e['goods_id']<=0x00ffffff for e in entries):
        raise ValueError('Invalid or repeated packed goods ID')
    numeric=any(e.get('token') for e in entries)
    numeric_events=redemption_events(entries) if numeric else []
    texts=[];nodes={};labels={}
    def text(s):
        i=TEXT_BASE+len(texts);texts.append(dict(id=i,text=s));return i
    for slot in range(3):
        for e in entries:labels[f'{slot}:{e["index"]}']=text(f'候选 {slot+1}：{e["name"]}')
    def cmd(i,*args):return dict(bank=1,id=i,args=[expression(integer(a)) if isinstance(a,int) else expression(a) for a in args])
    def work(i):return integer(100)+integer(i)+b'\x85'
    def go(t):return dict(eval='41a1',target=t)
    def eq(raw,v,t):return dict(eval=expression(raw+integer(v)+b'\x95'),target=t)
    def node(n,entry=None,conditions=None,template=None,modal=False):
        if n in nodes:raise ValueError('Duplicate state')
        nodes[n]=dict(name=n,entry=entry or [],conditions=conditions or [],template=template,modal=modal)
    def page(n,items,back):
        node(n,template='clear',conditions=[go(n+'_items')])
        node(n+'_items',entry=[cmd(149,i+1,label,-1,i+1,0) for i,(label,_) in enumerate(items)],conditions=[go(n+'_wait')])
        node(n+'_wait',template='show',conditions=[go(n+'_dispatch'),go(back)],modal=True)
        node(n+'_dispatch',conditions=[eq(integer(23)+b'\x84',i+1,t) for i,(_,t) in enumerate(items)]+[go(back)])
    def request(n,op,payload,target):
        node(n,entry=[cmd(100,1,0),cmd(100,3,0),cmd(100,2,payload),cmd(100,1,op)],conditions=[go(n+'_ack')])
        node(n+'_ack',conditions=[eq(work(3),-1,'error'),dict(eval=expression(work(3)+integer(1)+b'\x94'),target=target)],modal=True)
    if numeric:
        have_token=integer(61)+integer(TOKEN_EFFECT)+b'\x85'
        node('entry_router',conditions=[eq(have_token,1,'numeric_begin'),go('root')])
        node('numeric_begin',entry=[cmd(11,READY_FLAG,0)],conditions=[go('numeric0')])
        choices=[e for e in entries if e.get('custom')]
        for pi in range((len(choices)+5)//6):
            items=[(text(e['name']),f'redeem_check{e["index"]}') for e in choices[pi*6:pi*6+6]]
            if pi:items.append((text('上一页'),f'numeric{pi-1}'))
            if (pi+1)*6<len(choices):items.append((text('下一页'),f'numeric{pi+1}'))
            items.append((text('稍后选择（保留本次机会）'),'exit'))
            page(f'numeric{pi}',items,'exit')
        for e in choices:
            node(f'redeem_check{e["index"]}',conditions=[eq(have_token,1,f'redeem{e["index"]}'),go('exit')])
            node(f'redeem{e["index"]}',entry=[cmd(11,e['redeem_flag'],1)],conditions=[go('redeem_wait')])
        node('redeem_wait',conditions=[eq(have_token,0,'exit')],modal=True)
    page('root',[(text('原训练用品／设置'),'original'),(text('NRE 潜在能力测试'),'connect'),(text('离开'),'exit')],'exit')
    node('original',template='original',conditions=[go('root')],modal=True)
    node('exit',conditions=[go(2)])
    node('connect',entry=[cmd(100,i,v) for i,v in enumerate(MARKERS)],conditions=[go('connected')])
    node('connected',conditions=[eq(work(3),1,'refresh0')],modal=True)
    for slot in range(3):
        request(f'refresh{slot}',10+slot,0,f'label{slot}')
        # Populate the three choices serially; native talk list retains each label.
        node(f'label{slot}',entry=[cmd(149,slot+1,work(3),-1,slot+1,0)],conditions=[go(f'refresh{slot+1}' if slot<2 else 'editor_tail')])
    # Clear only once before serial label queries.
    nodes['connected']['conditions'][0]['target']='editor_clear'
    node('editor_clear',template='clear',conditions=[go('refresh0')])
    node('editor_tail',entry=[cmd(149,4,text('生成潜在能力'),-1,4,0),cmd(149,5,text('返回'),-1,5,0)],conditions=[go('editor_wait')])
    node('editor_wait',template='show',conditions=[go('editor_dispatch'),go('root')],modal=True)
    node('editor_dispatch',conditions=[eq(integer(23)+b'\x84',s+1,f'categories{s}') for s in range(3)]+[eq(integer(23)+b'\x84',4,'spawn'),go('root')])
    for s in range(3):
        categories=list(dict.fromkeys(e['category'] for e in entries))
        page(f'categories{s}',[(text(c),f'pick{s}_{ci}_0') for ci,c in enumerate(categories)]+[(text('返回'),'editor_clear')],'editor_clear')
        for ci,c in enumerate(categories):
            group=[e for e in entries if e['category']==c]
            count=(len(group)+5)//6
            for page_index in range(count):
                items=[(text(e['name']),f'select{s}_{e["index"]}') for e in group[page_index*6:page_index*6+6]]
                if page_index>0:items.append((text('上一页'),f'pick{s}_{ci}_{page_index-1}'))
                if page_index+1<count:items.append((text('下一页'),f'pick{s}_{ci}_{page_index+1}'))
                items.append((text('返回分类'),f'categories{s}'))
                page(f'pick{s}_{ci}_{page_index}',items,f'categories{s}')
        for e in entries:request(f'select{s}_{e["index"]}',100+s,e['index'],'editor_clear')
    request('spawn_request' if numeric else 'spawn',200,0,'trigger')
    if numeric:node('spawn',conditions=[eq(have_token,1,'numeric_begin'),go('spawn_request')])
    node('trigger',entry=[cmd(11,FLAG,1)],conditions=[go('exit')])
    page('error',[(text('配置未就绪，请返回重试'),'editor_clear'),(text('离开'),'exit')],'exit')
    ids={n:STATE_BASE+i for i,n in enumerate(nodes)}
    for n,v in nodes.items():
        v['id']=ids[n]
        for c in v['conditions']:c['target']=ids.get(c['target'],c['target'])
    return dict(states=list(nodes.values()),texts=texts,labels=labels,root_state=ids['entry_router' if numeric else 'root'],state_first=STATE_BASE,state_end=STATE_BASE+len(nodes),entries=entries,pool_ids=POOL_IDS,request_flag=FLAG,spawn_reference_entities=[10000404,10000405],numeric_events=numeric_events,token_goods=TOKEN_GOODS if numeric else None,ready_flag=READY_FLAG,auto_open_eval=expression(integer(15)+integer(READY_FLAG)+b'\x85'+integer(1)+b'\x95'))

def encode_pool(original,offset,goods,allowed=None):
    if len(original)!=36 or offset!=8 or not 0<goods<=0x00ffffff or goods not in (allowed if allowed is not None else (*range(8900000,8900006),8000000,8010000,8020000,8100000,8200000,8200500)):
        raise ValueError('Unapproved training pool or good')
    data=bytearray(original);struct.pack_into('<i',data,offset,goods);return bytes(data)
