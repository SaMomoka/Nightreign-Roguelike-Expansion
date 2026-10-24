# 运行时接口复核（2026-10-20）

本轮目标是核实玩家身份、当前 SpEffect 和远征生命周期接口，为按玩家去重、叠层上限、结束清理寻找可接入的实际依据。

| 来源 | 本轮直接观察 | 对项目的结论 |
|---|---|---|
| [fromsoftware-rs](https://github.com/vswarte/fromsoftware-rs) 与 [nightreign 0.14.0 文档](https://docs.rs/nightreign/0.14.0/nightreign/) | 仓库同时支持多个游戏；Nightreign 公开 API 入口仅列出 `param` 模块 | 参数绑定存在，不能据此声称具备 Nightreign 玩家或事件适配器 |
| [apply-speffect 示例](https://github.com/vswarte/fromsoftware-rs/blob/main/examples/apply-speffect/src/lib.rs) | 示例导入的是 `eldenring`，不是 `nightreign` | 不能将其 WorldChrMan、任务调度及效果应用接口填入本项目 Nightreign 映射 |
| [NR Sandbox 作者页面](https://www.nexusmods.com/eldenringnightreign/mods/783) | 作者标明当前测试目标为 Nightreign 1.3.3.0；离线单人，带 native runtime；不包含正常远征进程和 Seamless | 存在该游戏的原生运行时先例，但公开说明不足以证明可复用的身份、远征、奖励或同步 API |

以上仅是来源复核，未下载运行第三方 DLL，未引入第三方源码。没有根据搜索标题借用其他游戏的偏移或函数。`integration/phase1_native_rewards.json` 中 identity_contract 仍为 null，机制去重和动态权重实现状态仍为 false。

本地具备 .NET SDK 8.0.402、用于参数工具的 PowerShell7/.NET10；本轮 PATH 中未找到 cargo/rustc/cl/cmake。工具链存在也不能替代游戏接口的证据。

接下来的运行时取证需要能定位到本机版本的 Nightreign 玩家/效果结构，以及可区分进入远征、死亡复活、返回圆桌和断线重连的实际信号；还需确认回调线程和多人所有权。在得到依据前不生成伪接口或直接写内存。本轮继续完成可验证的参数包整合，见 `14-combined-packages.md`。
