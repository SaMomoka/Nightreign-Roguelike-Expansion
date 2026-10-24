# 局内 Buff：第一批原生奖励接入

用户已验收当前遗物配置里程碑，并要求继续任务书。本轮转入 Phase 1。
这次交付的是能构建、加载、回滚的原生奖励池实验，尚不是 Phase 1 全部验收。

## 已实现

六项效果复用本机原生潜在力量，保留效果、图标和显示数值：

|效果|Goods / PermanentBuff / SpEffect ID|原生字段|值|
|---|---|---|---|
|生命上限|8000000|maxHpRate|1.10|
|FP上限|8010000|maxMpRate|1.10|
|精力上限|8020000|maxStaminaRate|1.10|
|物理攻击|8100000|physicsAttackRate|1.06|
|物理减伤|8200000|slash/blow/thrust/neutralDamageCutRate|0.88|
|属性减伤|8200500|magic/fire/thunder/darkDamageCutRate|0.88|

这六项为原生效果接入，不能算六种新增机制已完成实机验证。
引用按 `ItemTableParam.itemId → EquipParamGoods.vagrantItemLotId → PermanentBuffParam.spEffectId`
核对；Goods字段虽然保留旧名称，当前NR元数据明确引用PermanentBuffParam。
只按相同ID猜测会漏掉这一层，不采用该做法。

`data/phase1_native_buffs.json`配置六项池内权重，默认由100改为200。
作用范围仅为池4200100，不是所有敌人、所有潜在力量池。其余9项保留100。
静态权重总和从1500到2100，六项目标合计权重比例从40%到约57.14%；
实际出现概率还受上游奖励、职业、旗标等条件影响，不把该比例宣称为实测概率。
保留disableParam_NT和unknown字段，不猜测其运行语义。

## 两个隔离包

项目根目录：

- `启动局内Buff实验.cmd`：只加载六处权重修改。
- `启动三选一实验.cmd`：额外将ItemLotParam_enemy的6000050/6000051已有正权重引用改到4200100。

两包均使用独立NRE存档，从已有测试种子复制一次，保留后续进度；正式存档、游戏目录不改动。
游戏需先完全退出。实验包由`local/phase1/*-package.json`定位，资源在`local/packages`。
每次玩局内Buff实验都要使用带补丁启动；这与遗物“生成一次后撤补丁”的用法不同。

无补丁回滚对照：

```powershell
python tools/phase1_package.py rollback --mode weighted
python tools/phase1_package.py rollback --mode three_choices_probe
```

回滚停用参数覆盖，不抹掉当前隔离存档已取得的原生奖励；验证下一远征清理需要实际进入新远征。

## 三选一证据与限制

原件NpcParam43510020（堡垒骑士队长）和44700010（堡垒掳人少女人偶）
的rewardItemLot_1指向6000050；6000050、6000051为武器表路径，6000052指向潜在力量池4200100。
NR元数据将ItemLot标为连续ID，原生三条连续记录提供了复用奖励界面的实验入口。
“这三条对应三个选择槽”仍是待实机验证的推断。
实验将前两条正权重的7个引用改为同一潜在力量池，保留第三条及其余字段。
会替换此共享堡垒奖励路径的武器选项，因此与基础权重版分开。
同轮可能重复、菜单如何显示、取消后是否刷新，均不能仅由参数断言。

[Nightreign EMEDF](https://soulsmods.github.io/emedf/nr-emedf.html)的通用对话接口列出0/1/2按钮，
未提供可直接宣称可用的任意三卡奖励UI。因此本轮先复用原生首领奖励路径，不虚构菜单API。

## 构建及审计

```powershell
pwsh -File tools/verify_phase1_exports.ps1
python tools/phase1_package.py build --mode weighted
python tools/phase1_package.py build --mode three_choices_probe
python tools/check_phase1_build.py --pwsh (Get-Command pwsh).Source
python tools/validate.py
python -m unittest discover -s tests
```

构建固定原件SHA256和内部版本10350000。六张CSV全部核对行顺序与相关字段。
ItemTableParam有重复ID，补丁采用“表ID+原始行序+物品/类别/条件原值”定位；
不能使用只按ID覆盖行的方式。构建后解密比较全部资源和单元格。
输出改变为6处或13处，其余资源不变。坏行序、坏引用条件、权重溢出与缺少条件必须拒绝。
包签核为散列完整性检查，不是数字签名或游戏运行证明。

## 每项效果的联合实机验收方案

一次远征统一记录：职业、等级、遗物、武器、获得前后、重复获得、倒地救起、最终死亡及新远征。
升级会影响面板，须在同级比较；战斗效果使用同目标、同武器、同动作和相同距离。

|效果|首选验证|额外对照|
|---|---|---|
|生命|选择前后最大生命|当前生命变化与上限变化分开记录|
|FP|选择前后最大FP|相同法术可施放次数|
|精力|选择前后精力上限|相同攻击连续次数|
|物理攻击|同目标同动作物理伤害|不把暴击/反击算收益|
|物理减伤|同敌同物理攻击受伤|属性伤害对照|
|属性减伤|同敌同属性攻击受伤|物理伤害对照|

每项再获取一次，分别检验加算/乘算/覆盖，不能预设原生叠加符合任务书。
新远征同等级恢复基线才可勾选清理通过；复活后不重复加层才可勾选复活通过。
用户已授权无需逐项打断询问，未观察的结果留待统一验收，不填造数据。

## Phase 1 剩余

- 三项潜在力量选择的实际界面、提交与重复候选行为。
- 六项效果在本补丁下的获取、重复叠加、复活与远征清理。
- 可配置加算层数上限；原生行为尚未证明符合任务书。
- 按玩家构筑动态权重、机制去重、刷新事务、玩家/远征身份及事件适配。
- 无缝联机与重连。没有可用网络接口证据前不写假API。

目前没有把Python离线抽奖器作为游戏实现，也没有启用未验证的15类机制定义。
