# 研究来源与证据边界

检索日期：2026-10-20。以下为作者仓库、工具专用定义或发行商原文；本轮没有复制第三方代码。main 分支可能变化，正式映射前须锁定 commit、工具版本、游戏散列。

- **S01** [Smithbox 官方说明](https://github.com/vawser/Smithbox)：支持 Nightreign 参数编辑；不能由此确认所有机制。

- **S02** [NR 参数类型表](https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/PARAM/NR/Param%20Type%20Info.json)：确认 NR 类型，包括 AttachEffect、CoolTime、Buddy、行为和攻击表；表存在不代表原生使用。

- **S03** [NR AttachEffectTable 元数据](https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/PARAM/NR/Param%20Meta/AttachEffectTableParam.xml)：attachEffectId 指向 AttachEffectParam；chanceWeight / chanceWeight_dlc 存在。

- **S04** [NR AttachEffect 元数据](https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/PARAM/NR/Param%20Meta/AttachEffectParam.xml)：onHitSpEffect、passiveSpEffectId_1/2/3、职业过滤、compatibilityId/exclusivityId、文本和图标引用存在。

- **S05** [NR SpEffect 元数据](https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/PARAM/NR/Param%20Meta/SpEffectParam.xml)：maxHpRate、maxMpRate、maxStaminaRate、攻击与伤害削减倍率字段存在；行 ID 和生效条件未知。

- **S06** [NR 武器元数据](https://github.com/vawser/Smithbox/blob/main/src/Smithbox.Data/Assets/PARAM/NR/Param%20Meta/EquipParamWeapon.xml)：spEffectBehaviorId0 引用 SpEffectParam；不能推出所有背包被动的范围。

- **S07** [DarkScript3 发布页](https://github.com/AinTunez/DarkScript3/releases)：3.6.3 可见；3.6.2 添加 NR 1.03 指令并指出部分未知、复杂事件回编译例外。

- **S08** [Nightreign EMEDF](https://soulsmods.github.io/emedf/nr-emedf.html)：有计时、距离、事件值、伤害来源和角色状态条件；并非任意技能回调 API。

- **S09** [Mod Engine 3 官方仓库](https://github.com/garyttierney/me3)：支持 Nightreign 和 Windows；Apache-2.0/MIT（logo 例外）。

- **S10** [MMV + Seamless 作者配置](https://github.com/eepycloud/More-Map-Variations-MMV-Seamless-Coop)：仅配置先例；nrsc.dll 的 load_early=true、离线启动；报告使用旧版组合，不保证本机兼容。

- **S11** [Seamless 作者页面](https://www.nexusmods.com/eldenringnightreign/mods/3)：独立存档、1–6 玩家；作者未保证其他 Mod 兼容；不得未经许可修改或再分发。

- **S12** [Rolling Pool Editor 作者仓库](https://github.com/ip1259/Rolling_Pool_Editor)：声明支持普通、深夜、Debuff 池以及基于 1.03.5 的输出；属于权重修改先例。

- **S13** [Rolling Pool Editor Smithbox 指南](https://github.com/ip1259/Rolling_Pool_Editor/blob/master/SMITHBOX_GUIDE_en.md)：外部配置与 Smithbox CSV 路线参考；本项目不采用其内置游戏资源。

- **S14** [官方 Hotfix 1.03.5](https://en.bandainamcoent.eu/elden-ring/news/elden-ring-nightreign-hotfix-1035)：2026-03-31：App 1.03.2、Regulation 1.03.5；不据此宣称用户安装版本。

- **S15** [官方 1.03.2 更新](https://www.bandainamcoent.com/news/elden-ring-nightreign-patch-notes-version-1-03-2)：说明官方存在武器类别动作调整和召唤灵体行为；不是可调用接口证明。

- **S16** [ME3 发布页](https://github.com/garyttierney/me3/releases)：安装包与发布说明入口，需固定实际下载版本及散列。

- **S17** [Smithbox 发布页](https://github.com/vawser/Smithbox/releases)：工具版本选择入口，需确认 NR 数据版本。

工具网页支持只算资料证据。所有 NRE Buff 的“已验证”必须由本机实机记录支持。没有找到特定机制先例时明确记录“未找到”；这不代表社区一定不存在。

许可证：ME3 的双许可证已见于官方说明；其他工具仅链接使用，未核验的具体源文件许可证不推定可复用。Rolling Pool Editor 和 MMV 配置仓库本轮未确认明确授权文本，不复制其实现或打包资源。Seamless 仅由用户从作者页面安装。
