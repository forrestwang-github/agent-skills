# 安装与更新

本文面向希望使用本仓库 Skill 的用户。先根据目的选择方式；安装单个 Skill 不要求预先安装管理器。

## 先选择使用方式

| 你的目的 | 推荐方式 |
|---|---|
| 安装一个或少量 Skill | 把目标 Skill 的固定版本子目录链接直接交给 Agent |
| 长期管理多个 Skill | 先按相同方法安装 `skill-repository-manager`，再用对话检查、安装和更新 |
| 手动审查、离线安装或归档 | 从 GitHub Release 下载 ZIP，并核对 SHA-256 |
| 评估尚未发布的最新开发内容 | 使用 `main` 分支链接，并接受内容可能变化的风险 |

## 直接安装一个 Skill

稳定使用优先选择具体 Skill 的版本标签，不直接依赖持续变化的 `main`。标签格式为：

```text
<skill-name>-v<major.minor.patch>
```

例如，当前 `book-knowledge-guide v1.0.0` 的固定版本地址是：

```text
https://github.com/forrestwang-github/agent-skills/tree/book-knowledge-guide-v1.0.0/skills/personal-learning/book-knowledge-guide
```

后续版本只需替换标签中的版本号。各 Skill 的最新正式标签以仓库 README 和 `registry/catalog.json` 为准，不要依据 GitHub 仓库全局的 “Latest” 标识判断。

将对应 Skill 的 GitHub 子目录链接交给支持 GitHub Skill 安装的 Agent，并要求它安装到自己的 Skill 搜索目录。安装后新建会话，使 Agent 重新发现 Skill。

可以直接对 Agent 说：

> 请从这个 GitHub 子目录安装 Skill。安装完成后告诉我安装目录、实际版本和验证结果。

不同 Agent 的目录、清单和元数据格式可能不同。下载成功不代表该 Agent 一定兼容 Codex 风格的 `SKILL.md` 或 `agents/openai.yaml`；应以目标 Agent 的安装说明为准。

## 使用管理器维护多个 Skill

`skill-repository-manager` 是可选工具，不是其他 Skill 的安装前置条件。需要持续管理多个 Skill 时，先从 README 的 Skill 目录第一行取得它的固定版本链接，并按上一节的方法安装。

安装管理器并新建会话后，可以用自然语言要求 Agent：

- 检查某个 Skill 是否有更新。
- 安装或更新指定 Skill。
- 比较源码与安装副本。
- 回滚最近一次由管理器执行的更新。

安装、更新和回滚默认先展示预览，确认后才修改文件。管理器会记录由它安装的版本和内容摘要；如果安装副本已被手工修改，更新默认停止，避免覆盖本地改动。

## 手动下载和验证 Release ZIP

正式版本的 GitHub Release 会提供 Skill ZIP 和 `.sha256` 文件。ZIP 适合审查、归档或交给不支持 GitHub 子目录安装的环境。解压后应确认 Skill 根目录中存在 `SKILL.md` 和与仓库根目录一致的 `LICENSE`。

Windows PowerShell 可以计算下载文件的哈希：

```powershell
Get-FileHash .\book-knowledge-guide-v1.0.0.zip -Algorithm SHA256
```

Linux 或安装了 `sha256sum` 的环境可以计算下载文件的哈希：

```bash
sha256sum book-knowledge-guide-v1.0.0.zip
```

将输出的哈希值与 Release 中 `.sha256` 文件的第一列比较，两者必须一致。校验只能证明下载内容与发布附件一致，不能代替对 Skill 权限、脚本和数据处理边界的审查。未来发布生成的校验文件只记录 ZIP 文件名，因此也可以在两个文件位于同一目录时使用 `sha256sum -c`。

## 何时使用 `main`

`main` 代表当前开发状态，不保证内容和行为固定。例如：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/skills/personal-learning/book-knowledge-guide
```

只有在评估尚未发布的修复或功能时才使用 `main`。日常使用和可复现环境应固定到版本标签；升级时先比较版本差异和本地修改，并保留可回滚副本。
