# 发布指南

本文只面向本仓库维护者。普通用户安装或更新 Skill 请阅读 `docs/INSTALLATION.md`，不需要执行这里的 Git 或发布操作。

## 推荐方式：通过对话发布

可以直接要求已安装 `skill-repository-manager` 的 Agent：

> 准备发布 `<skill-name>`，请检查变更并建议语义化版本。

管理器先输出当前版本、目标版本、变更文件、提交信息、标签、Release 标题和验证结果。只有维护者明确确认最近一次预览后，才执行提交、推送、标签和 GitHub Release 等外部变更。如果文件、HEAD、版本或目标标签在确认前发生变化，必须重新准备发布。

## 发布前条件

- 目标 Skill 已在 `registry/catalog.json` 注册。
- `SKILL.md`、引用文件和 Agent 元数据校验通过。
- Skill 内的 `LICENSE` 与仓库根许可证完全一致。
- 目标 Skill 自己的测试和确定性校验通过；通用发布命令只保证仓库结构校验，不自动推断每个 Skill 的专用测试命令。
- 工作区只包含预期变更，不含凭据、本地样本或生成产物。
- 当前分支和 GitHub 远程与 `registry/repository.json` 一致。
- 目标标签在本地和远端都不存在。

## 新增公开 Skill

先把源码放入 `skills/<category>/<skill-name>/`，再通过对话要求管理器登记，或先预览以下命令：

```powershell
python skills/tooling/skill-repository-manager/scripts/skillctl.py --repo-root . --json register sample-skill --category work --version 0.1.0
```

确认后增加 `--yes`。登记会更新 `registry/catalog.json`、复制 Apache-2.0 许可证，并重新生成 README 的受控 Skill 目录。若只需修复许可证副本或重建目录，使用 `sync`，同样先预览再确认。

仅限本机使用的 Skill 不应登记到公开目录；应放在被 Git 忽略的 `private/` 中。

## 完整发布事务

确认发布后，管理器依次执行：

1. 更新 `registry/catalog.json` 中的版本和标签，并同步 README 的稳定版链接。
2. 重新校验目标 Skill。
3. 提交并推送 `main`。
4. 创建并推送带注释标签。
5. 创建 GitHub Release。
6. GitHub Actions 打包 Skill ZIP 并生成 SHA-256。
7. 等待对应标签的 GitHub Actions 完成。
8. 核验 Release、ZIP、SHA-256 和固定版本目录链接。
9. 输出完整验收结果。

发布不会强制推送、覆盖既有标签或重写历史。

## 中断与恢复

发布包含多个不可逆的远端步骤。网络或 GitHub Actions 故障可能发生在提交、标签或 Release 已创建之后；此时不要删除或重建已经成功的对象，应先确认断点，再从安全步骤继续。

如果标签和 Release 已存在，只是最终验收中断，可以运行只读验收：

```powershell
python skills/tooling/skill-repository-manager/scripts/skillctl.py --repo-root . --json verify-release skill-repository-manager --tag skill-repository-manager-v1.1.0
```

`verify-release` 会等待对应工作流，并检查 ZIP、SHA-256 和固定版本目录链接。它不会修改 Git 或 GitHub 状态。

## Release 内容

Release Notes 建议说明主要变化、修复、不兼容项、安装链接和更新建议。默认自动生成的 Release Notes 可能只包含 Git 提交摘要；重要版本应提供人工整理的说明。附件至少包括：

```text
<skill-name>-v<version>.zip
<skill-name>-v<version>.sha256
```

ZIP 必须可以作为独立 Skill 安装，并包含 `SKILL.md` 和 Apache License 2.0 许可证副本。
