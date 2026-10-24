# 两人协作开发

## 开始前

仓库当前为公开仓库。所有提交均可公开阅读；账号凭据、正式或测试存档、游戏资源、工具二进制、第三方表格及本机配置不提交。保留 .gitignore 的 local/ 与二进制排除规则。是否更改可见性由仓库所有者决定。

所有者在仓库 Settings → Collaborators → Add people 邀请朋友的 GitHub 用户名；朋友接受后即可协作。无需共享密码或账号。

## 获取和验证

```powershell
git clone https://github.com/SaMomoka/Nightreign-Roguelike-Expansion.git
cd Nightreign-Roguelike-Expansion
python tools/validate.py
python -m unittest discover -s tests -v
```

建议 Windows，Python 3.9+。基础设计校验和纯逻辑测试不代表实机功能完成；依赖本地资源的检查可能跳过或要求先准备资源。实机构建还需 PowerShell 7、当前受支持游戏版本、自行取得的 Smithbox / SoulsFormats、Mod Engine 3，以及由本人合法游戏提取的数据。参考 docs/05-toolchain-experiment.md、docs/18-full-relic-catalog.md、docs/19-full-relic-runtime.md。

local/ 不在仓库中。克隆后不能直接双击启动脚本获得完整测试包。完整遗物构建目前还依赖本地旧编辑器包及导出的目录；新机器自动初始化尚未完成。不得复制他人的游戏路径、用户存档路径或绝对地址。测试必须使用独立 NRE 存档和离线环境。

## 每轮流程

1. 在 docs/20-team-tasks.md 或 GitHub Issue 中认领一项任务，写明文件范围和基准提交。
2. 同步 main，再创建个人任务分支，例如 codex/relic-menu 或 codex/build-portability。
3. 各自只修改认领范围；参数改动保存表名、行 ID、字段、旧值与新值，避免互传覆盖 regulation.bin。
4. 完成后运行相关测试、unittest 和 tools/validate.py，填写交接记录。
5. 推送任务分支并创建 Pull Request，由另一人检查后合并到 main；指定一人负责整合构建与实机测试。

```powershell
git switch main
git pull --ff-only
git switch -c codex/your-task
# 完成修改及检查后，只添加本任务文件
git add <本任务文件>
git commit -m "Describe the change"
git push -u origin codex/your-task
```

main 保留可追踪基线，不强制推送、不互相覆盖分支。修改共享构建脚本、菜单状态号、参数行号或文本号之前先约定归属并检查冲突。建议所有者通过仓库规则要求 PR 和至少另一人审查；本次未自动修改仓库权限或规则。

## GPT 任务提示与交接

开始时让各自的 GPT 读取 AGENTS.md、CONTRIBUTING.md、任务记录与实际 Git 状态。共享聊天不能替代仓库同步，也不代表另一端 GPT 已看到最新文件。

```text
任务：
负责人／分支：
基于提交：
允许修改的文件与参数范围：
完成内容：
验证命令与结果：
实机已证实范围：
尚未验证／已知问题：
对另一人的影响及下一步：
```
