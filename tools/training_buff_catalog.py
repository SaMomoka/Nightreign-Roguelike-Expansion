"""Catalog native obtainable permanent buffs from verified local exports.

Quest key items share goodsType 11 but are not latent-power rewards; retain an
explicit exclusion audit. No name lists or raw game resources are distributed.
"""
import hashlib,json
from phase1_rewards import load_tables,unique

def category(goods_id):
    if goods_id<8000000:return '特殊区域赐福'
    if goods_id<8100000:return '生命、FP、精力'
    if goods_id<8330000:return '攻击、防御、抗性'
    if goods_id<8380000:return '法术、技艺、绝招'
    if goods_id<8500000:return '闪避、防御与行动'
    if goods_id<8600000:return '卢恩与自动攻击'
    return '命中、恢复与异常'

def build_catalog(root):
    tables=load_tables(root)
    text=json.loads((root/'local/evidence/training-text.json').read_text(encoding='utf-8-sig'))
    for source in text['sources']:
        path=root/'local/native-menu/original'/source['path']
        if hashlib.sha256(path.read_bytes()).hexdigest().upper()!=source['sha256'].upper():
            raise ValueError('Training text source changed')
    names=text['languages']['zhocn']['name']
    entries=[];excluded=[]
    for good in sorted(tables['EquipParamGoods'],key=lambda x:int(x['ID'])):
        if int(good['goodsType'])!=11:continue
        gid=int(good['ID'])
        if 45000<=gid<46000:
            excluded.append(dict(goods_id=gid,reason='quest_key_item_not_latent_reward'));continue
        permanent=unique(tables['PermanentBuffParam'],int(good['vagrantItemLotId']))
        effect=int(permanent['spEffectId']);effect_row=unique(tables['SpEffectParam'],effect)
        text_id=int(effect_row['spEffectTextId_1'])
        name=names.get(str(text_id))
        if not name:
            if gid in (2,11,12,6000500):
                excluded.append(dict(goods_id=gid,reason='special_area_or_key_item_without_native_reward_text'));continue
            raise ValueError('Missing native name: '+str(gid))
        value=int(permanent['numericValue'])
        if value and int(permanent['displayNumericValue']):
            name+=f' {value:+d}'+('%' if int(permanent['displayPercentageSymbol']) else '')
        entries.append(dict(goods_id=gid,name=name,category=category(gid),source_permanent=int(permanent['ID']),source_effect=effect,text_id=text_id))
    if not entries:raise ValueError('Empty native catalog')
    return dict(entries=entries,audit=dict(native_count=len(entries),excluded=excluded,scope='All goodsType=11 with valid permanent/effect references except quest key items; includes named special-area blessings',sources=text['sources']))
