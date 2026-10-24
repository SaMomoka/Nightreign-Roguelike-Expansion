# 本机参数取证（2026-10-20）

适用本机 App 1.03.3、Regulation 1.03.5；regulation 内部版本 10350000。
标题画面已观察为脱机模式。版本相同不代表其他整合包参数相同，构建仍固定 SHA256。

## 已完成

- 原游戏和整合包只读取证；原 regulation 已复制到 local/inputs。
- 官方 Smithbox 2.2.6 便携版安装于 local/tools。项目启用 NR 专用参数定义。
- 导出 297 个 CSV；原 regulation 容器为 252 个文件，两者口径不同。
- 以原版存档副本 NRE_EXP001.sl2 启动纯 ME3，进入圆桌厅堂/训练场；未加载 Seamless 或其他整合包 DLL。
- 用户确认训练场无法装备护符，所以原护符方案改为消耗品实验。
- tools/build_exp001.ps1 使用版本过滤后的 NR PARAMDEF，写入后重新解密并比较全表全部单元格；
  仅 SpEffectParam[500830].maxHpRate 从 1 改为 1.05，其余 251 个资源内容散列一致。

## 真实引用

|来源|引用或值|证据范围|
|---|---|---|
|EquipParamGoods 830 煮熟虾子|refId_default=500830、refCategory=2|与 SpEffect 同 ID 对照|
|SpEffect 500830|maxHpRate=1、effectEndurance=60|实验改为1.05，保留其他字段|
|EquipParamAccessory 1000 红琥珀链坠|spEffectId_1=310000|训练场无法装备，本轮不用此入口|
|AttachEffect 310000|passiveSpEffectId_1=310000|SpEffect310000 maxHpRate=1.12|
|AttachEffect 6610400|SpEffect7610400|maxHpRate=1.1|
|SpEffect7033200 / 7270100|additionalCharacterSkillUse=1|追踪者/铁眼特定职业原生技艺额外次数|
|SpEffect 字段|characterSkillCooldownReduction、ultimateArtGaugeRate、ultimateArtGauge、ultimateArtGaugeRecovery、ultimateArtGaugeChargeRate|字段存在，具体刷新语义未验证|
|EquipParamAntique|relicColor、isDeepRelic、attachEffectTableId_1/2/3、attachEffectTableId_curse1/2/3|普通/深夜及正负池入口|
|AntiqueStandParam|heroType、relicSlot1/2/3、deepRelicSlot1/2/3、unlockFlag、goodsId|容器槽位入口，颜色编码/合法性尚待对照|

SpEffect 有 13472 行、AttachEffect 2079 行、效果池22088行、CoolTime40行、容器74行。
学者强化道具存在独立 SpEffect：不得用学者强化虾子替代本实验基础道具。
上述是数据证据，不能据此宣称游戏行为、叠层上限或无缝同步已验证。

## 隔离与回滚

原版基线 local/baseline.me3；实验 local/exp001.me3；均离线并使用 NRE_EXP001.sl2。
实验资源 local/exp001/mod/regulation.bin；不放入游戏目录，也不覆盖整合包。
游戏完全退出后切换 profile 再启动，恢复 baseline 即停止加载补丁。
local/mod 中 Smithbox 保存的文件不是本实验的加载文件。
未通过校验的中间产物使用 .unverified.bin 等名称，不由实验 profile 加载。

## 尚未完成

已通过用户手动实测：最大生命1517→1593（理论1592.85），持续时间正常。
用户已确认到期恢复1517，切回原版配置后前后均1517；尚缺同伤害承受；
重复使用/倒地/复活/远征清理以及双人同步均未完成。
只有这些实机记录支持的行为才能更新验收结果。当前 F 最小数值/持续时间实验通过，扩展测试未验收。
