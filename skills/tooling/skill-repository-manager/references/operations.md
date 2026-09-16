# 本地安装与更新操作

## 默认环境

- 唯一源码：`E:\AI Workspace\skills`
- Codex Skill 根目录：优先读取仓库根目录 `.skillctl.local.json`；其次使用 `CODEX_HOME/skills`；最后使用用户目录 `.codex/skills`。
- 安装账本：目标 Skill 根目录下 `.managed-skills.json`
- 备份：目标 Skill 根目录下 `.skillctl/backups/<skill>/<timestamp>`

## 只读流程

先执行 `verify`。涉及安装副本时再执行 `status` 或 `diff`。涉及 GitHub 更新时执行 `check`。用 `--json` 获取结构化结果。

## 新 Skill 登记

业务内容由 Skill 创建流程完成后，使用 `register <skill> --category <category>` 登记。预览应包含分类、路径、初始版本、描述、许可证动作和 README 更新；确认后才传入 `--yes`。

登记会把根 `LICENSE` 同步到 Skill、更新 `registry/catalog.json`，并重建 README 中 `skill-catalog` 标记之间的表格。`SECURITY.md`、`docs/` 和 README 其他段落不自动改写。已有登记、路径冲突、frontmatter 名称不一致或登记后校验失败时停止。

根许可证变更或目录表不一致时，先预览 `sync`，确认后执行 `sync --yes`。同步只处理已登记 Skill 的许可证副本和 README 受控目录。

## 链接

`link` 适合当前开发电脑，让 Agent 直接读取唯一源码。目标已存在时默认拒绝；只有用户确认后才使用 `--replace --yes`，原目录必须先进入备份位置。

Windows 创建目录链接可能需要开发者模式或管理员权限。失败时不要改为静默复制；说明原因并让用户选择安装副本。

## 安装和更新

首次安装使用 `install`。已有安装使用 `update`，不要用安装强行覆盖。更新前比较内容摘要和安装账本；检测到本地修改时停止，让用户决定保留、迁回源码或覆盖。

本地开发测试可以使用 `--source local`。稳定环境使用 GitHub 发布标签。安装成功后执行 `status` 验证，并提示新会话加载。

## 回滚

仅恢复由管理器创建的最近备份。预览备份版本和目标路径后再执行 `rollback --yes`。不要回滚未由管理器记录的目录。

## 自定义 Agent

没有适配器时使用 `--dest <绝对路径>`。先确认该 Agent 实际扫描该目录；下载成功不等于 Agent 一定兼容 `SKILL.md` 或 `agents/openai.yaml`。
