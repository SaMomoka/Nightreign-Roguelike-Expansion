"""Owned numeric reward definitions and native two-step redemption events.

Goods IDs fit the packed 24-bit payload. Pool, event and lot IDs are separate
namespaces. Unknown attack/movement speed mappings are deliberately absent.
"""
import struct

TOKEN_GOODS=8900999
READY_FLAG=10009881
SELECT_FLAG=10009900
LOT_BASE=1900640000
EVENT_BASE=10009900

def extra_entries(start):
    rates={k:1.03 for k in ('physicsAttackRate','magicAttackRate','fireAttackRate','thunderAttackRate','darkAttackRate')}
    specs=[
        ('魔力伤害 +3%',8100500,dict(magicAttackRate=1.03,fireAttackRate=1,thunderAttackRate=1,darkAttackRate=1),3),
        ('魔法威力 +3%',8330103,dict(rates,magParamChange=1,miracleParamChange=0),3),
        ('祷告威力 +3%',8330103,dict(rates,magParamChange=0,miracleParamChange=1),3),
        ('魔力承伤 -4%',8200500,dict(magicDamageCutRate=.96,fireDamageCutRate=1,thunderDamageCutRate=1,darkDamageCutRate=1),4),
        ('精力恢复 +2',8020200,dict(staminaRecoverChangeSpeed=2),2),
        ('技艺冷却 -5%',8370000,dict(characterSkillCooldownReduction=.95),5),
    ]
    return [dict(index=start+i,goods_id=8900010+i,name='NRE '+name,category='NRE 数值强化',source_goods=src,source_permanent=src,source_effect=src,fields=fields,numeric_value=value,custom=True) for i,(name,src,fields,value) in enumerate(specs)]

def instruction(bank,op,fmt,*args):
    return dict(bank=bank,id=op,hex=struct.pack(fmt,*args).hex())

def redemption_events(entries):
    ins=instruction
    events=[dict(id=READY_FLAG,instructions=[
        ins(2003,66,'<B3xIB3x',0,READY_FLAG,0),
        ins(3,4,'<bB2xiB3x',0,3,TOKEN_GOODS,1),
        ins(1001,0,'<f',1.0),
        ins(2003,66,'<B3xIB3x',0,READY_FLAG,1),
        ins(3,4,'<bB2xiB3x',0,3,TOKEN_GOODS,0),
        ins(1000,4,'<B3x',1)])]
    for i,e in enumerate(x for x in entries if x.get('custom')):
        # All choices share one serialized event (below); flags are requests only.
        e['redeem_flag']=SELECT_FLAG+i;e['redeem_lot']=LOT_BASE+i
    # One dispatcher, no wait between consumption and award. Restart clears
    # every request, so simultaneously set flags cannot redeem one token twice.
    choices=[e for e in entries if e.get('custom')]
    dispatch=[ins(2003,66,'<B3xIB3x',0,e['redeem_flag'],0) for e in choices]
    dispatch += [ins(3,0,'<bBBxI',-1,1,0,e['redeem_flag']) for e in choices]
    dispatch += [ins(0,0,'<bBb x',0,1,-1),
                 ins(3,4,'<bB2xiB3x',1,3,TOKEN_GOODS,1),
                 ins(1000,2,'<BBb x',1,0,1)]
    for e in choices:
        dispatch += [ins(1003,1,'<BBBxI',3,0,0,e['redeem_flag']),
                     ins(2003,24,'<B3xii',3,TOKEN_GOODS,1),
                     ins(2003,107,'<i',e['redeem_lot']),
                     ins(1000,4,'<B3x',1)]
    dispatch.append(ins(1000,4,'<B3x',1))
    events.append(dict(id=EVENT_BASE,instructions=dispatch))
    return events
