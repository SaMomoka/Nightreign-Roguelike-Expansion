# 工具链与首个游戏内实验

## 固定环境

|组件|已确认|
|---|---|
|游戏|D:\\Steam\\steamapps\\common\\ELDEN RING NIGHTREIGN\\Game；标题 App1.03.3 / Regulation1.03.5|
|Smithbox|官方2.2.6，项目 local/mod，NR专用定义；使用 Smithbox.OpenGL.exe|
|ME3|用户整合包 bin/me3.exe，文件版本0.10.1；纯ME3离线基线已启动|
|Seamless|用户整合包 nrsc.dll 已取散列；版本未能由文件属性确认，本实验不加载|
|DarkScript3|已研究官方发布3.6.3；本机事件编译未验证|

原件 SHA256：876A3CA279A4561D0C69F81FE5E510C75C59AB9A8A201694F8CF4A42C91E0268。
Smithbox 下载包 SHA256：9a147c319dccad4b6dd2a5adcc6f2ba3a5c11c40b079520c05260cb19994b3d7。
来源 https://github.com/vawser/Smithbox/releases/tag/2.2.6 。
详细行证据见 [本机证据](08-local-evidence.md)。

## EXP-001：煮熟虾子额外 +5% 最大生命

训练场不能装备护符，改用基础煮熟虾子（Goods830→SpEffect500830）。
原 maxHpRate=1，改为1.05，持续60秒及其他字段保持原样。
这是原生道具效果修改，不代表新奖励池、叠层系统或遗物配置器已实现。

构建工具 tools/build_exp001.ps1 固定输入散列、版本和原值，使用 Smithbox 附带库；
需要 PowerShell7/.NET10，当前运行环境已验证。它先写候选文件、回读比较所有单元格及其他资源，
通过后才命名为可加载的 regulation.bin。已有输出时拒绝覆盖。
报告 local/evidence/EXP-001-build.json 显示仅1格变化，其余251个资源未变。

实测顺序：
1. 原版 baseline profile：固定职业/等级/装备，记录使用前后最大HP。
2. 退出游戏，加载 local/exp001.me3，同一条件记录使用前后HP，预计比值接近1.05，记录取整。
3. 验证60秒到期恢复、同伤害来源的实际承受、重复使用、倒地/复活、远征结束清理。
4. 退出并恢复 baseline profile，检查HP回到基线，游戏原件与正式存档散列未改变。
5. 单人通过后才单独加入Seamless测试；双人换房主对照。

验收记录 tests/ingame/EXP-001.json。目前 MINIMAL_SINGLE_PLAYER_PASS：用户报告1517→1593、持续时间正常、到期恢复1517，撤除补丁后前后均1517。重复使用/倒地复活/远征清理及双人仍待测。
自动化键盘输入未能可靠打开游戏菜单，实机动作由用户协助；不得据参数回读冒充游戏成功。

## 合并与事件边界

多个 regulation.bin 不能靠加载顺序自动合并。应基于同一原件按表/行/字段三方合并；
同字段不同改值拒绝自动处理。版本变化后先重新取证，不盲写旧ID。
DarkScript3事件编译、空闲旗标、状态观察和无修改回编译尚待验证；
当前没有提供虚构 CLI，也没有生成未经验证的事件文件。
