# GitHub 发布策略

## 默认发布配置

- 仓库：`forrestwang-github/agent-skills`
- 可见性：public
- 分支：`main`
- 标签：`<skill-name>-v<major.minor.patch>`
- 版本：语义化版本
- 用户确认：最终发布前一次

## 版本判断

- patch：向后兼容的修正、措辞调整、小范围行为纠正。
- minor：向后兼容的新能力、新参考文件或新操作模式。
- major：删除或重命名关键能力、改变默认路径或输出契约、需要使用者迁移。

无法可靠判断时只准备预览并请求用户选择，不自行提升 major。

## 发布前条件

- Skill 校验通过。
- Git 仓库、远程和当前分支符合配置。
- GitHub CLI 已登录。
- 标签不存在。
- 未提交改动仅限 `skills/<category>/<skill-name>` 和 `registry/catalog.json`。
- 不包含密钥、令牌、私钥或不应公开的本地资料。

## 发布预览

展示：Skill、当前版本、目标版本、版本类型、变更文件、提交信息、目标远程、分支、标签、Release 标题、验证结果和风险提示。

只有用户明确确认最近一次预览后才执行相同参数的 `release --yes`。如果文件、HEAD、版本或标签状态变化，原确认失效，重新预览。

## 发布事务

顺序为：更新 `registry/catalog.json`、校验、提交目标 Skill 与清单、推送分支、创建并推送标签、创建 GitHub Release、远程核验。

不强制推送、不覆盖标签、不自动删除远程对象。部分失败时保留已经成功的不可逆步骤并报告可安全重试的环节。
