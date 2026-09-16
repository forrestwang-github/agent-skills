---
name: skill-repository-manager
description: 通过自然语言管理本地 Skill 源码仓库和各 Agent 的安装副本，执行校验、状态检查、开发链接、安装、更新、差异比较、回滚及 GitHub 语义化发布。适用于用户要求管理、发布、安装或更新个人 Skill；不用于修改 Skill 的业务内容。
---

# Skill 仓库管理

## 目标

把用户的自然语言意图转换为可审计的 `skillctl.py` 操作。默认源码仓库为 `E:\AI Workspace\skills`，GitHub 仓库为 `forrestwang-github/agent-skills`。用户无需记忆命令。

用户指令优先于本 Skill。不要因为本 Skill 的默认值扩大用户要求的操作范围。

## 必读参考

- 安装、链接、更新或回滚时读取 [references/operations.md](references/operations.md)。
- 准备或执行 GitHub 发布时读取 [references/release-policy.md](references/release-policy.md)。

## 执行入口

脚本位于本 Skill 的 `scripts/skillctl.py`。优先使用当前 Skill 实际路径调用脚本，并显式传入：

```text
--repo-root E:\AI Workspace\skills
```

所有检查和预览使用 `--json`，根据结构化结果向用户解释。不要通过解析散乱终端文本推断是否成功。

## 意图映射

| 用户意图 | 命令 |
|---|---|
| 检查或验证 Skill | `verify` |
| 登记新开发的 Skill | `register`，不传 `--yes` |
| 同步许可证和 README 清单 | `sync`，不传 `--yes` |
| 查看安装状态 | `status` |
| 检查 GitHub 更新 | `check` |
| 查看源码与安装副本差异 | `diff` |
| 将本地开发目录接入 Agent | `link` |
| 安装 Skill | `install` |
| 更新已安装 Skill | `update` |
| 回滚最近更新 | `rollback` |
| 准备发布 | `release`，不传 `--yes` |
| 确认发布 | 用相同参数再次执行 `release --yes` |

## 安全边界

- `verify`、`status`、`check`、`diff` 以及不带 `--yes` 的 `register`、`sync` 和 `release` 是只读预览，可直接执行。
- `register --yes`、`sync --yes`、`link`、`install`、`update`、`rollback` 和 `release --yes` 会修改文件或外部状态。先展示脚本返回的计划，再取得一次明确确认。
- “发布”授权一次完整发布事务：更新版本、提交、推送、创建标签和 GitHub Release。若用户只说“准备发布”或“看看能不能发布”，不得执行外部变更。
- 不绕过 GitHub 登录、系统沙箱、分支保护或权限审批。
- 不使用强制推送，不删除远程标签，不重写 Git 历史。
- 检测到目标目录本地修改、非预期仓库改动、标签冲突或验证失败时停止并说明。
- 发布失败时报告已完成的步骤，不以破坏性操作自动回滚远程状态。

## 对话方式

用户可以直接说“登记新 Skill 到 work”“同步许可证和 README”“检查所有 Skill”“安装 book-knowledge-guide”“更新到最新版”“准备发布 book-knowledge-guide”“确认发布”或“回滚上次更新”。

登记新 Skill 时读取 `SKILL.md` 的名称和描述，写入 `registry/catalog.json`，同步根许可证到 Skill，并只重写 README 的受控目录区块。根 `LICENSE`、`SECURITY.md` 和 `docs/` 是仓库级政策文件，不因新增 Skill 自动改写。

准备发布时给出：当前版本、建议版本、变更范围、验证结果、提交信息、目标分支、标签和 Release 标题。确认发布必须与最近一次预览的 Skill、版本和 Git 状态一致；若状态变化，重新预览。

## 完成验证

每次修改操作后再次执行相应只读命令，确认目标版本、路径、链接或发布状态。告诉用户何时需要新建 Agent 会话才能加载变更。
