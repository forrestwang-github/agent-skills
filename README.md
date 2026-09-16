# Agent Skills

个人 Agent Skill 的唯一源码仓库。每个一级子目录包含一个独立 Skill；`skill-repository-manager` 提供校验、安装、更新、回滚和语义化发布能力。

稳定使用者应安装带版本标签的 Skill 子目录，不直接依赖 `main`。示例标签：`book-knowledge-guide-v1.1.0`。

## 对话使用

安装 `skill-repository-manager` 后，可以直接告诉 Agent：

- 检查所有 Skill。
- 安装或更新某个 Skill。
- 准备发布某个 Skill。
- 确认发布。
- 回滚上次更新。

管理操作默认先预览；安装、更新、回滚和发布在确认后执行。

