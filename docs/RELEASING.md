# 发布指南

## 发布前条件

- 目标 Skill 已在 `registry/catalog.json` 注册。
- `SKILL.md`、引用文件和 Agent 元数据校验通过。
- Skill 内的 `LICENSE` 与仓库根许可证完全一致。
- 目标 Skill 自己的测试和确定性校验通过；通用发布命令只保证仓库结构校验，不自动推断每个 Skill 的专用测试命令。
- 工作区只包含预期变更，不含凭据、本地样本或生成产物。
- 当前分支和 GitHub 远程与 `registry/repository.json` 一致。

## 推荐流程

使用 `skill-repository-manager` 通过自然语言准备发布。管理器先输出当前版本、目标版本、变更文件、提交信息、标签和 Release 标题；获得一次明确确认后，再执行完整发布事务。

新增 Skill 时，先把源码放入 `skills/<分类>/<skill-name>/`，再用 `register` 登记。先查看预览，确认后增加 `--yes`：

```powershell
python skills/tooling/skill-repository-manager/scripts/skillctl.py --repo-root . register <skill-name> --category <分类> --version 0.1.0
```

登记会更新 `registry/catalog.json`、复制 Apache-2.0 许可证，并重新生成 README 的 Skill 清单。若只需修复许可证副本或重建清单，则使用 `sync`，同样先预览再确认应用。

发布顺序为：

1. 更新 `registry/catalog.json` 中的版本和标签，并同步 README 的稳定版链接。
2. 重新校验目标 Skill。
3. 提交并推送 `main`。
4. 创建并推送带注释标签。
5. 创建 GitHub Release。
6. GitHub Actions 打包 Skill ZIP 并生成 SHA-256。
7. 等待对应标签的 GitHub Actions 完成。
8. 核验 Release、ZIP、SHA-256 和固定版本目录链接。
9. 输出完整验收结果。

不强制推送，不覆盖既有标签，不以重写历史的方式修复发布失败。部分步骤失败时，应保留已成功的远端状态并从安全步骤重试。远端发布已存在但验收中断时，可以执行：

```powershell
python skills/tooling/skill-repository-manager/scripts/skillctl.py --repo-root . --json verify-release skill-repository-manager --tag skill-repository-manager-v1.1.0
```

## Release 内容

Release Notes 建议说明主要变化、修复、不兼容项、安装链接和更新建议。默认自动生成的 Release Notes 可能只包含 Git 提交摘要；重要版本应提供人工整理的说明。附件至少包括：

```text
<skill-name>-v<version>.zip
<skill-name>-v<version>.sha256
```

ZIP 必须是可独立安装的 Skill 目录，并包含 Apache License 2.0 许可证副本。
