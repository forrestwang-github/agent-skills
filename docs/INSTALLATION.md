# 安装与更新

## 选择版本

稳定使用优先选择具体 Skill 的版本标签，不直接依赖持续变化的 `main`。标签格式为：

```text
<skill-name>-v<major.minor.patch>
```

例如，当前 `book-knowledge-guide v1.0.0` 的固定版本地址是：

```text
https://github.com/forrestwang-github/agent-skills/tree/book-knowledge-guide-v1.0.0/skills/personal-learning/book-knowledge-guide
```

后续版本只需替换标签中的版本号。各 Skill 的最新正式标签以仓库 README 和 `registry/catalog.json` 为准，不要依据 GitHub 仓库全局的 “Latest” 标识判断。

需要评估最新开发内容时，可使用：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/skills/personal-learning/book-knowledge-guide
```

## 交给 Agent 安装

将对应 Skill 的 GitHub 子目录链接交给支持 GitHub Skill 安装的 Agent，并要求它安装到自己的 Skill 搜索目录。安装后新建会话，使 Agent 重新发现 Skill。

可以直接对 Agent 说：

> 请从这个 GitHub 子目录安装 Skill。安装完成后告诉我安装目录、实际版本和验证结果。

不同 Agent 的目录、清单和元数据格式可能不同。下载成功不代表该 Agent 一定兼容 Codex 风格的 `SKILL.md` 或 `agents/openai.yaml`；应以目标 Agent 的安装说明为准。

## 选择安装来源

| 来源 | 适用场景 | 稳定性 |
|---|---|---|
| 带版本标签的 Skill 子目录 | 交给 Agent 自动安装 | 推荐，内容固定 |
| GitHub Release ZIP | 手动下载、审查、离线安装或归档 | 推荐，附带校验文件 |
| `main` 分支 Skill 子目录 | 评估尚未发布的最新开发内容 | 可能随时变化 |

## 使用仓库管理 Skill

安装 `skill-repository-manager` 后，可以用自然语言要求 Agent：

- 检查某个 Skill 是否有更新。
- 安装或更新指定 Skill。
- 比较源码与安装副本。
- 回滚最近一次由管理器执行的更新。

安装、更新和回滚默认先展示预览，确认后才修改文件。

## 验证来源

正式版本的 GitHub Release 会提供 Skill ZIP 和 `.sha256` 文件。ZIP 内必须包含与仓库根目录一致的 `LICENSE`。

Windows PowerShell 可以计算下载文件的哈希：

```powershell
Get-FileHash .\book-knowledge-guide-v1.0.0.zip -Algorithm SHA256
```

Linux 或安装了 `sha256sum` 的环境可以计算下载文件的哈希：

```bash
sha256sum book-knowledge-guide-v1.0.0.zip
```

将输出的哈希值与 Release 中 `.sha256` 文件的第一列比较，两者必须一致。校验只能证明下载内容与发布附件一致，不能代替对 Skill 权限、脚本和数据处理边界的审查。未来发布生成的校验文件只记录 ZIP 文件名，因此也可以在两个文件位于同一目录时使用 `sha256sum -c`。
