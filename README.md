# Nightreign Roguelike Expansion

共同开发仓库：[SaMomoka/Nightreign-Roguelike-Expansion](https://github.com/SaMomoka/Nightreign-Roguelike-Expansion)。原开发工作区位于 `E:\Codex\Project\黑环mod`；协作者可以使用自己的本地目录。
依据 `writing-block.md` V2.0，当前已有实验参数补丁和本地遗物配置器；单件三词条的生成、持久保留和卸下清理已实测，完整NRE玩法尚未完成。

## 共同开发

先阅读 [协作与环境说明](CONTRIBUTING.md) 和 [任务及交接记录](docs/20-team-tasks.md)。仓库只包含原创源码、配置和验证记录，不含游戏资源、存档、工具二进制及可直接运行的整合包。

## 元素连击设计更新（2026-10-26）

[BUFF-001 元素连击设计与待定项](docs/elemental-combo/README.md)：元素标记附着敌人，达到一定连击数触发；每个敌人独立冷却，小型 6 秒、精英 8 秒、Boss 10 秒。冷却期间暂停积累连击与元素标记，期间命中不缓存补算；结束后新的有效命中恢复积累，到期不自动触发。连击阈值、元素选择和触发后的状态消耗仍待定。本次仅记录设计，未修改规则代码，未运行自动测试或实机验证。

## 阅读顺序

1. [第一轮交付与阻塞](docs/00-delivery.md)
2. [技术可行性矩阵](docs/01-feasibility.md)
3. [Buff 归类](docs/02-buff-catalog.md)
4. [抽取、叠加和联动](docs/03-rules.md)
5. [遗物配置验证](docs/04-relics.md)
6. [工具链与最小实机实验](docs/05-toolchain-experiment.md)
7. [联机、图标和版本管理](docs/06-engineering.md)
8. [来源及证据边界](docs/07-sources.md)
9. [遗物真实数据审计及原型](docs/09-relic-data-audit.md)
10. [本地遗物配置器与生成包](docs/10-relic-configurator.md)

## 本地检查

Python 3.9+（本机3.9.1已验证），仅标准库，无需 pip：

```powershell
Set-Location 'E:\Codex\Project\黑环mod'
python tools/validate.py
python -m unittest discover -s tests -v
```

`data/buffs.json` 保留全部 15 个方向。这15类局内Buff条目默认关闭；遗物生成真实映射另见 integration/relic_generator.json。
`tools/validate.py` 验证设计数据，不生成 regulation.bin。
`integration/mappings.json` 必须在真实版本取证后填写；运行 `python tools/validate.py --release`
会在未绑定游戏版本与未验证效果时拒绝发布，这是预期行为。

目录：data（定义）、rules（设计）、integration（真实映射）、build（构建约定）、
relic_configurator（配置输入契约）、compatibility（联机模板）、tests（校验和实机记录）、
tools（工具）、docs（报告）、assets（图标规范）。游戏原件、导出资源和工具放 ignored 的 local/。


## 当前开发：Phase 1 原生奖励

遗物配置实验版已由用户验收，继续局内Buff。
已接入六项原生数值效果的可配置奖励权重，并构建独立三选一可行性实验包。
根目录`启动局内Buff实验.cmd`和`启动三选一实验.cmd`分别启动隔离版本。
详见[局内Buff接入、用法与验收边界](docs/11-phase1-native-rewards.md)。
这批是参数构建通过，尚未实机确认菜单、叠加、复活和远征清理；Phase 1未标记完成。

局内配置窗口：双击`启动局内Buff配置器.cmd`。新增分类三选一模式，通过生存/攻击/防御互不重叠的原生候选池避免跨槽重复。详见[本轮进展与限制](docs/12-phase1-choice-workbench.md)。用户已暂缓实机验证；当前只验收工具和参数结构。

新增“分层三选一”模式：普通/稀有两层权重接入项目专用原生池，包含26项现有效果，不改原共享池。见[分层候选与概率说明](docs/13-phase1-tiered-pools.md)。实机验证继续暂缓。

遗物与局内奖励现在可生成同一个整合包：双击 `构建整合实验包.cmd`，随后可用 `启动整合实验包.cmd` 选择“生成＋奖励 / 仅奖励 / 无补丁对照”。三者共用独立测试存档，构建不会启动游戏。见[整合包用法和验证边界](docs/14-combined-packages.md)。

新增游戏内菜单实验：小壶商人的原生对话菜单加入“NRE 遗物选择”，可通过原生商店选择和购买本包预设。使用 `启动游戏内菜单实验包.cmd`；不需要在运行时打开外部配置窗口。**简中单人隔离存档的菜单、预设商品页、返回和购买现已实机通过；其他玩法与多人尚未验收。**详见[原生菜单接入与限制](docs/16-native-menu.md)。

新增四遗物制作编辑器：两个普通、两个深夜入口，每页三条词条选择、1 暗痕制作及返回。使用 `启动遗物制作实验包.cmd`；当前候选为普通 20 种、深夜 63 种组合，构建检查通过，新版实机验收待完成。新成品需要持续加载 Mod 定义。详见[编辑器用法与验收边界](docs/17-relic-editor.md)。

全量词条扩展：用户已确认上一版制作正常。附件与本机参数对照后，目录含普通 406 条、深夜正面 326 条和负面 24 条；全量原生分页菜单及无窗口后台制作模块已构建并启动隔离测试，完整制作结果尚待实机确认。使用 `启动全量遗物制作实验包.cmd`；旧版入口保留。见[全量编辑器用法和验证边界](docs/19-full-relic-runtime.md)。
