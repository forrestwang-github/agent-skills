# model-private-skill

面向 AgentSkills/SKILL.md 兼容 Agent 的模型私有化推理部署规划 skill。先收集模型、负载和服务目标，再按固定 HTML 格式生成厂商中立的 GPU、CPU、内存、存储、公网用户接入带宽、部署框架及拓扑建议；信息不足时先追问，不直接给出单一精确卡数。

## 环境要求

- 支持AgentSkills/SKILL.md的Agent；
- Python 3.10及以上；
- Agent能够执行本地Python脚本；
- Agent能够搜索并打开官方网页、仓库原始文件和PDF。

Python核心没有第三方运行时依赖。

## 从 GitHub 安装

本 Skill 由统一仓库 `forrestwang-github/agent-skills` 发布。支持从 GitHub 子目录安装的 Agent，可以使用精确版本链接：

```text
https://github.com/forrestwang-github/agent-skills/tree/model-private-skill-v<VERSION>/model-private-skill
```

开发分支地址仅用于查看最新源码，不建议作为稳定安装版本：

```text
https://github.com/forrestwang-github/agent-skills/tree/main/model-private-skill
```

完整使用方式和固定 HTML 输出格式见 [SKILL.md](SKILL.md) 及 [HTML 输出模板](core/model_private_skill/references/html-output-template.md)。

## 更新

已安装版本由 `skill-repository-manager` 或目标 Agent 的 Skill 安装器管理。更新前应比较新旧版本、检查本地修改并保留回滚点；不要在安装目录中直接执行 `git pull`。

## 使用

部署完成后直接通过自然语言向Agent提出需求，例如：

```text
请帮我规划Qwen系列某模型的私有化推理配置。
典型输入2000 Token，典型输出500 Token，
典型并发16，峰值并发64，
P95 TTFT要求2秒，单请求生成速度30 Token/s。
```

## 输出边界

- 用户可见结果固定为可直接打开的独立 HTML 文件，内嵌 CSS；先给部署结论，再给资源配置、GPU 选型建议、估算过程、部署注意事项和证据来源；
- 输出`economic`和`peak_production`两档方案；
- GPU候选不等于云实例、库存或可售性；
- 不输出云实例SKU、价格、报价或采购结论；
- 找不到合格性能基准时，不承诺Token/s、TTFT或ITL；
- 模型、GPU、引擎和性能证据必须遵守[来源策略](core/model_private_skill/references/source-policy.md)。

## 本地检查

```text
python cli/model-private-skill.py validate-input --input examples/7b-request.json
python cli/model-private-skill.py calculate --input examples/7b-request.json
python cli/model-private-skill.py gpu validate
```

## 自动选型与确定性交付

hardware_profile 是可选字段。省略时，calculate 先输出每副本客观显存需求，并生成每档最多三个按单卡可用显存、TP/PP 对齐和节点边界计算的 GPU 组合；提供时，仅评估客户已有硬件。

完成资料核实后，必须按以下链路交付：

1. calculate 生成 calculation.json；
2. 将模型和框架的合格证据及框架结论写入 verified-enrichment.json；
3. build-plan 将两者组装为 schema 1.5 的 result.json；
4. validate-output 校验 result.json；
5. render-html 将已校验 result.json 生成独立 UTF-8 HTML。

框架必须引用已核实的引擎兼容性证据。render-html 拒绝渲染未通过 JSON 校验的计划。
