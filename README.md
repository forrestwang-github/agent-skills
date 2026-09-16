# Agent Skills

个人 Agent Skill 的公开源码仓库。可安装 Skill 统一位于 `skills/`，仓库注册信息位于 `registry/`；`skill-repository-manager` 提供校验、安装、更新、回滚和语义化发布能力。

稳定使用者应安装带版本标签的 Skill 子目录，不直接依赖 `main`。示例标签：`book-knowledge-guide-v1.1.0`。

## Skill 目录

<!-- skill-catalog:start -->
| Skill | 分类 | 最新稳定版 | 安装 | 用途 |
|---|---|---|---|---|
| [`aliyun-bill-analysis-skill`](skills/work/aliyun-bill-analysis-skill/) | work | [`v1.0.0`](https://github.com/forrestwang-github/agent-skills/releases/tag/aliyun-bill-analysis-skill-v1.0.0) | [固定版本](https://github.com/forrestwang-github/agent-skills/tree/aliyun-bill-analysis-skill-v1.0.0/skills/work/aliyun-bill-analysis-skill) | 分析阿里云账单并生成费用、用量及趋势报告。 |
| [`model-private-skill`](skills/work/model-private-skill/) | work | 未正式发布 | [查看 main](skills/work/model-private-skill/) | 规划模型私有化推理所需的厂商中立资源和拓扑。 |
| [`book-knowledge-guide`](skills/personal-learning/book-knowledge-guide/) | personal-learning | 未正式发布 | [查看 main](skills/personal-learning/book-knowledge-guide/) | 深度解读非虚构书籍并沉淀到 Obsidian。 |
| [`tech-factor-analysis-html-report`](skills/personal-learning/tech-factor-analysis-html-report/) | personal-learning | 未正式发布 | [查看 main](skills/personal-learning/tech-factor-analysis-html-report/) | 研究技术主题并生成知识库 Markdown 与 HTML 报告。 |
| [`skill-repository-manager`](skills/tooling/skill-repository-manager/) | tooling | 未正式发布 | [查看 main](skills/tooling/skill-repository-manager/) | 通过对话校验、安装、更新和发布个人 Skill。 |
<!-- skill-catalog:end -->

当前版本和正式发布标签以 [`registry/catalog.json`](registry/catalog.json) 为准。

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
skills/             按使用场景分类的可安装 Skill 源码
  work/              工作场景
  personal-learning/ 个人学习与知识沉淀
  tooling/           Skill 开发和仓库管理工具
```

从 GitHub 安装单个 Skill 时，使用 `skills/<category>/<skill-name>` 子目录。例如：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/skills/personal-learning/book-knowledge-guide
```

完整的版本选择、安装、更新和校验说明见 [安装文档](docs/INSTALLATION.md)。

## 版本与发布

每个 Skill 独立采用语义化版本，标签格式为 `<skill-name>-v<version>`。正式 Release 包含可独立安装的 ZIP 和 SHA-256 校验文件。维护规则见 [版本规则](docs/VERSIONING.md) 和 [发布指南](docs/RELEASING.md)。

## 安全

不要把访问令牌、云账号 AK/SK、私钥、个人数据或内部样本提交到仓库。安全问题请按 [安全政策](SECURITY.md) 私密报告。

## License

本仓库中的代码、Skill 指令、提示词和文档均采用 [Apache License 2.0](LICENSE) 授权，另有明确声明的第三方内容除外。每个可独立安装的 Skill 都携带同一许可证副本。
