# 版本与兼容性

本文面向 Skill 使用者和仓库维护者，解释如何判断稳定版本、升级影响以及 GitHub 标签的含义。

## 1. 用户应该看什么

普通用户判断最新版时，优先查看仓库 README 中对应 Skill 的“最新稳定版”和“固定版本”链接。不要把 `main` 或 GitHub 仓库全局的 “Latest” 标识当作某个 Skill 的稳定版本依据。

本仓库采用 monorepo：多个 Skill 共用一个 Git 仓库，但每个 Skill 独立维护版本。

## 2. 注册表字段

`registry/catalog.json` 是版本和路径的机器可读来源：

| 字段 | 含义 |
|---|---|
| `version` | 该 Skill 当前登记的语义化版本号 |
| `release_tag` | 最新正式发布对应的不可变 Git 标签 |
| `release_tag: null` | 尚未正式发布，只能视为开发状态 |
| `path` | Skill 在仓库中的目录 |

正式版本必须同时具有匹配的 `version` 和 `release_tag`。只有版本号、没有标签，并不构成可复现的正式发布。

## 3. 语义化版本

- `PATCH`：向后兼容的修正、措辞调整或小范围行为纠正。
- `MINOR`：向后兼容的新能力、新参考资料或新操作模式。
- `MAJOR`：删除或重命名关键能力、改变默认路径或输出契约、要求使用者迁移。

仓库目录整理、文档改进和 CI 变化如果不改变 Skill 的安装内容或行为，不单独提升每个 Skill 的版本。

## 4. 标签和 Release

标签格式为：

```text
<skill-name>-v<major.minor.patch>
```

标签指向完整仓库快照，但 Release ZIP 只打包对应 Skill。已发布标签不覆盖、不移动，也不通过重写历史修正。

GitHub 的 “Latest” 标识是整个仓库级别的，只能指向一个 Release，不能表示每个 Skill 的最新版本。判断某个 Skill 的最新稳定版本时，以 README 和 `registry/catalog.json` 中该 Skill 的 `release_tag` 为准。

## 5. 开发版与升级

`main` 表示当前开发状态，不保证路径和行为始终不变。稳定安装应固定到版本标签。

升级前建议确认：

1. 目标版本属于 PATCH、MINOR 还是 MAJOR。
2. Release Notes 是否包含行为变化或迁移要求。
3. 本地安装副本是否有手工修改。
4. 是否保留了可以回滚的旧版本。
