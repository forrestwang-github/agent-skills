# Agent Skills

个人 Agent Skill 的公开源码仓库。可安装 Skill 统一位于 `skills/`，仓库注册信息位于 `registry/`；`skill-repository-manager` 提供校验、安装、更新、回滚和语义化发布能力。

稳定使用者应安装带版本标签的 Skill 子目录，不直接依赖 `main`。示例标签：`book-knowledge-guide-v1.0.0`。

## Skill 目录

<!-- skill-catalog:start -->
<table>
  <thead>
    <tr><th>分类</th><th>Skill</th><th>最新稳定版</th><th>安装</th><th>用途</th></tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="1">工具（tooling）</td>
      <td><a href="skills/tooling/skill-repository-manager/"><code>skill-repository-manager</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/releases/tag/skill-repository-manager-v1.1.1"><code>v1.1.1</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/tree/skill-repository-manager-v1.1.1/skills/tooling/skill-repository-manager">固定版本</a></td>
      <td>通过对话校验、安装、更新和发布个人 Skill。</td>
    </tr>
    <tr>
      <td rowspan="2">工作（work）</td>
      <td><a href="skills/work/aliyun-bill-analysis-skill/"><code>aliyun-bill-analysis-skill</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/releases/tag/aliyun-bill-analysis-skill-v1.0.0"><code>v1.0.0</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/tree/aliyun-bill-analysis-skill-v1.0.0/skills/work/aliyun-bill-analysis-skill">固定版本</a></td>
      <td>分析阿里云账单并生成费用、用量及趋势报告。</td>
    </tr>
    <tr>
      <td><a href="skills/work/model-private-skill/"><code>model-private-skill</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/releases/tag/model-private-skill-v1.0.0"><code>v1.0.0</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/tree/model-private-skill-v1.0.0/skills/work/model-private-skill">固定版本</a></td>
      <td>规划模型私有化推理所需的厂商中立资源和拓扑。</td>
    </tr>
    <tr>
      <td rowspan="2">个人学习（personal-learning）</td>
      <td><a href="skills/personal-learning/book-knowledge-guide/"><code>book-knowledge-guide</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/releases/tag/book-knowledge-guide-v1.0.0"><code>v1.0.0</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/tree/book-knowledge-guide-v1.0.0/skills/personal-learning/book-knowledge-guide">固定版本</a></td>
      <td>深度解读非虚构书籍并沉淀到 Obsidian。</td>
    </tr>
    <tr>
      <td><a href="skills/personal-learning/tech-factor-analysis-html-report/"><code>tech-factor-analysis-html-report</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/releases/tag/tech-factor-analysis-html-report-v2.0.1"><code>v2.0.1</code></a></td>
      <td><a href="https://github.com/forrestwang-github/agent-skills/tree/tech-factor-analysis-html-report-v2.0.1/skills/personal-learning/tech-factor-analysis-html-report">固定版本</a></td>
      <td>研究技术主题并生成知识库 Markdown 与 HTML 报告。</td>
    </tr>
  </tbody>
</table>
<!-- skill-catalog:end -->

当前版本和正式发布标签以 [`registry/catalog.json`](registry/catalog.json) 为准。

## 选择使用方式

这里有三种不同场景，不需要为了安装一个 Skill 而先安装管理器：

| 你的目的 | 推荐方式 |
|---|---|
| 只安装一个或少量 Skill | 直接把上方“固定版本”链接交给 Agent，不需要 `skill-repository-manager` |
| 长期管理多个 Skill，需要检查更新、比较差异或回滚 | 先安装 `skill-repository-manager`，再通过对话管理其他 Skill |
| 开发并发布本仓库中的 Skill | 在本地仓库中使用 `skill-repository-manager` 的登记、校验和发布能力 |

## 快速开始：安装单个 Skill

1. 在上方表格中点击目标 Skill 的“固定版本”。
2. 复制打开后的 GitHub 子目录地址。
3. 把链接交给支持 GitHub Skill 安装的 Agent，例如：“请从这个 GitHub 子目录安装 Skill，完成后告诉我安装目录和验证结果。”
4. 安装完成后新建会话，使 Agent 重新发现 Skill。

固定版本子目录适合交给 Agent 安装；Release 页面中的 ZIP 适合手动下载、审查和归档。`main` 仅用于评估尚未发布的开发内容。

## 使用管理器安装和更新

`skill-repository-manager` 是可选的管理工具，不是安装其他 Skill 的前置条件。只有在需要持续管理多个 Skill 时，才建议先用上面的固定版本链接安装它；安装完成并新建会话后，可以直接告诉 Agent：

- 检查某个 Skill 是否有更新。
- 安装或更新某个 Skill。
- 比较源码与安装副本。
- 回滚上次更新。

安装、更新和回滚默认先预览，确认后执行。

## 维护本仓库

仓库维护者还可以通过对话要求 Agent：

- 登记新开发的 Skill。
- 同步许可证和 README 目录。
- 准备并确认发布某个 Skill。
- 验收已发布版本。

涉及文件、Git 或 GitHub 状态变更的操作会先展示计划，再请求确认。

## 仓库结构

```text
.github/workflows/  GitHub 校验与发布自动化
registry/           仓库配置和 Skill 目录
skills/             按使用场景分类的可安装 Skill 源码
  work/              工作场景
  personal-learning/ 个人学习与知识沉淀
  tooling/           Skill 开发和仓库管理工具
```

从 GitHub 安装单个 Skill 时，应使用带标签的 `skills/<category>/<skill-name>` 子目录。例如：

```text
https://github.com/forrestwang-github/agent-skills/tree/book-knowledge-guide-v1.0.0/skills/personal-learning/book-knowledge-guide
```

完整的版本选择、安装、更新和校验说明见 [安装文档](docs/INSTALLATION.md)。

## 版本与发布

每个 Skill 独立采用语义化版本，标签格式为 `<skill-name>-v<version>`。正式 Release 包含可独立安装的 ZIP 和 SHA-256 校验文件。维护规则见 [版本规则](docs/VERSIONING.md) 和 [发布指南](docs/RELEASING.md)。

## 安全

不要把访问令牌、云账号 AK/SK、私钥、个人数据或内部样本提交到仓库。安全问题请按 [安全政策](SECURITY.md) 私密报告。

## License

本仓库中的代码、Skill 指令、提示词和文档均采用 [Apache License 2.0](LICENSE) 授权，另有明确声明的第三方内容除外。每个可独立安装的 Skill 都携带同一许可证副本。
