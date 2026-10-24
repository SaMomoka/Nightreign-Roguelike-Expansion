# 遗物真实数据审计与原型使用

本报告仅验证表数据和引用，不把可读取等同于可装备。数据来自本机 Regulation1.03.5。
`verify_relic_exports.ps1` 已从固定散列原件逐行核对5张表的ID、顺序及分析所用关键字段，全部通过；
显示名称来自Smithbox名称库，不代表已核对游戏中文文本。完整资源目录保留在ignored的local中。

## 数据结果

- 遗物1397条：isDeepRelic=0为1175条，=1为222条；这不是玩家实际可获得物品数量。
- 词条池22088行组成1081组，其中109组合法重复行ID；导入器保留每一候选行及顺序。
- 效果2079条、容器74条、SpEffect13472条。
- 666条模板的已配置槽位在基础正权重视图下各有一个、且可解析的候选效果；DLC权重语义仍未确认。
- 遗物→池有151处未解析引用（涉及77条遗物），池→效果94处，效果→SpEffect1处。
  这些结果与原件一致；可能涉及占位/不可达内容或未解码规则，不直接判定原版数据错误。
- 深夜示例2000000同时引用正面池2000000与负面池3000000；只证明存在两个引用，不能证明任意跨池组合合法。

## 10条可追溯样本（不是游戏合法性正例）

|遗物ID|工具名称|槽位→池→效果|
|---|---|---|
|1000|Delicate Burning Scene|attachEffectTableId_1 → 707121100 → 7121100|
|1010|Delicate Drizzly Scene|attachEffectTableId_1 → 707120000 → 7120000|
|1020|Delicate Luminous Scene|attachEffectTableId_1 → 707122400 → 7122400|
|1030|Delicate Tranquil Scene|attachEffectTableId_1 → 707123300 → 7123300|
|1040|Polished Burning Scene|attachEffectTableId_1 → 707040300 → 7040300；attachEffectTableId_2 → 707040400 → 7040400|
|1050|Delicate Luminous Scene|attachEffectTableId_1 → 707040200 → 7040200|
|1060|Polished Tranquil Scene|attachEffectTableId_1 → 707030900 → 7030900；attachEffectTableId_2 → 707000202 → 7000202|
|1070|Polished Drizzly Scene|attachEffectTableId_1 → 707030700 → 7030700；attachEffectTableId_2 → 707000002 → 7000002|
|1080|Polished Burning Scene|attachEffectTableId_1 → 707002600 → 7002600；attachEffectTableId_2 → 707000901 → 7000901|
|1090|Polished Tranquil Scene|attachEffectTableId_1 → 707002700 → 7002700；attachEffectTableId_2 → 707000801 → 7000801|

## 可运行的只读原型

在项目根目录运行；输出文件必须不存在，以保留之前取证：

```powershell
python tools/relic_catalog.py import --csv-dir local/evidence --regulation local/inputs/regulation.bin --output local/evidence/relic-catalog-new.json
python tools/relic_catalog.py inspect --catalog local/evidence/relic-catalog.json --template-id 1040
```

inspect显示正负槽位和所有基础正权重候选，输出恒为draft_not_applicable。
不会改存档、生成regulation或声称解决颜色/互斥/职业/额度的游戏合法性。
通用CSV差异工具只适合唯一ID表；对词条池应使用保留行序号的分析器，不能去重后比较。

## 任务D结论

外部目录读取、候选查看与固定模板追踪已经可运行。精确自选组合仍未验证：
compatibilityId/exclusivityId和DLC权重的解释、深夜正负约束、物品生成时是否写入存档实例，
以及每玩家独立应用入口均须进一步研究。原型故意不提供游戏应用功能。

下一实验优先选择原生固定模板1040：先在隔离存档中核对游戏描述与两条效果，
再定位合法获取来源及生成时机。若改变模板只影响新生成物品，应在一次性测试副本中验证；
不得据此直接改正式存档。R01数据阶段通过，R01游戏文本/效果与R02–R05仍待验证。
