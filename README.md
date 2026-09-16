# Agent Skills

个人 Agent Skill 的唯一源码仓库。可安装 Skill 统一位于 `skills/`，仓库注册信息位于 `registry/`；`skill-repository-manager` 提供校验、安装、更新、回滚和语义化发布能力。

稳定使用者应安装带版本标签的 Skill 子目录，不直接依赖 `main`。示例标签：`book-knowledge-guide-v1.1.0`。

## 对话使用

安装 `skill-repository-manager` 后，可以直接告诉 Agent：

- 检查所有 Skill。
- 安装或更新某个 Skill。
- 准备发布某个 Skill。
- 确认发布。
- 回滚上次更新。

管理操作默认先预览；安装、更新、回滚和发布在确认后执行。

## 仓库结构

```text
.github/workflows/  GitHub 校验与发布自动化
registry/           仓库配置和 Skill 目录
skills/             可独立安装的 Skill 源码
```

从 GitHub 安装单个 Skill 时，使用 `skills/<skill-name>` 子目录。例如：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/skills/book-knowledge-guide
```
