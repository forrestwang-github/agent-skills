# 安装与更新

## 选择版本

稳定使用优先选择具体 Skill 的版本标签，不直接依赖持续变化的 `main`。标签格式为：

```text
<skill-name>-v<major.minor.patch>
```

例如：

```text
https://github.com/forrestwang-github/agent-skills/tree/book-knowledge-guide-v<VERSION>/skills/personal-learning/book-knowledge-guide
```

需要评估最新开发内容时，可使用：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/skills/personal-learning/book-knowledge-guide
```

## 交给 Agent 安装

将对应 Skill 的 GitHub 子目录链接交给支持 GitHub Skill 安装的 Agent，并要求它安装到自己的 Skill 搜索目录。安装后新建会话，使 Agent 重新发现 Skill。

不同 Agent 的目录、清单和元数据格式可能不同。下载成功不代表该 Agent 一定兼容 Codex 风格的 `SKILL.md` 或 `agents/openai.yaml`；应以目标 Agent 的安装说明为准。

## 使用仓库管理 Skill

安装 `skill-repository-manager` 后，可以用自然语言要求 Agent：

- 检查某个 Skill 是否有更新。
- 安装或更新指定 Skill。
- 比较源码与安装副本。
- 回滚最近一次由管理器执行的更新。

安装、更新和回滚默认先展示预览，确认后才修改文件。

## 验证来源

正式版本的 GitHub Release 会提供 Skill ZIP 和 `.sha256` 文件。下载后应比较 SHA-256；ZIP 内必须包含与仓库根目录一致的 `LICENSE`。
