---
name: model-private-skill
description: 先收集模型私有化推理的关键负载与服务要求，再将模型转换为厂商中立的 GPU、CPU、内存、存储、公网用户接入带宽、部署框架和拓扑建议。用于推理部署容量规划、GPU 选型和压测准备；不用于云实例、价格、采购、训练或全参数微调规划。
---

# 模型私有化推理部署规划

以本文件所在目录作为 Skill 根目录。完整读取并执行
[通用执行规则](prompts/system-prompt.md)。
## 目标与交互门槛

目标是回答“这个模型如何部署、需要什么资源、为什么这样选”，最终必须覆盖：

1. CPU、内存、系统盘/模型盘、共享存储、公网用户接入带宽和显存容量要求；
2. 推荐 GPU 型号及每副本/每节点/总数量；
3. 推荐部署框架、版本或 commit（能核实时）及选择理由；
4. 混合注意力、多模态、量化、并行、故障冗余、跨节点通信和压测等注意事项。

遵守以下对话顺序：

- 用户只给模型 ID，或关键负载/SLO 仍缺失时，不直接输出单一精确卡数；先一次性列出所有高影响追问，并等待补充。
- 用户补充部分信息后，只追问仍会改变 GPU 数、精度、拓扑、框架或资源配置的字段；可由官方资料核实的模型结构、权重大小、revision 不要求用户重复提供。
- 信息齐全后，先用一句话给部署结论，再给两档方案表，随后解释估算逻辑、假设、证据、风险和压测计划；不要把中间计算过程冒充成性能保证。
- 没有足够信息时可以给区间或显存下限，但必须明确“待补充什么、影响什么”，不伪造精确性能数字。

需求收集的字段、追问措辞和可采用默认值见
[输入需求规范](core/model_private_skill/references/requirements.md)。最终用户可见结果必须使用固定 HTML 模板，包含推荐部署框架；机器接口 JSON 仍可按需生成并校验。格式见
[HTML 输出模板](core/model_private_skill/references/html-output-template.md)和[输出协议](core/model_private_skill/references/output-schema.md)。

交付时必须生成独立的 UTF-8 HTML 文件，文件名使用 <规范化模型-id>-deployment-plan.html；文件必须可直接打开，并在最终回复中提供文件链接。HTML 的固定章节、五列资源表和资源导向估算过程以输出模板为准。GPU 选型应先说明示例型号并非唯一答案，再提供简单推算与精细推算两条路径；显存行只给每推理副本的客观需求，不写具体 GPU 型号。估算过程标题使用“序号 + 资源名：用途”，并在结论前以小字号备注解释专有名词或函数；每一个数值均须标明单位、来源或采用理由，公网带宽估算的输入下须以小字先说明本项只计算用户接入，再以“在实际部署中，还应注意”补充服务私网和跨节点 GPU 网络；分别直接输出峰值入向、峰值出向和二者较大值，不设置人为下限；公网入向只采用用户实测到达 RPS，流式出向按活跃流并发和单请求 Token/s，非流式出向按用户实测响应完成 RPS；缺失适用真实输入时带宽结果为 null，不得用并发或请求时长反推补齐；估算标签固定为“输入 / 估算过程 / 结果”，结果直接陈述；混合注意力或特殊算子须在首次出现处以小字说明作用、资源/兼容性影响和部署决策。

按任务阶段加载资料：

- 采集需求时读取[输入需求规范](core/model_private_skill/references/requirements.md)。
- 开始任何联网检索前，必须完整读取[证据来源策略](core/model_private_skill/references/source-policy.md)。
- 计算资源时读取[容量计算方法](core/model_private_skill/references/sizing-method.md)。
- 筛选 GPU 时读取[GPU 选择规则](core/model_private_skill/references/gpu-selection.md)。
- 生成交付结果时读取[输出协议](core/model_private_skill/references/output-schema.md)。

使用宿主 Agent 提供的搜索、网页读取或 HTTP 工具时，严格执行证据来源策略；工具名称可以不同，但允许的数据源、证据门槛和停止条件不得改变。

需要确定性计算时，使用 Python 3.10 及以上版本运行根目录下的通用命令：

```text
python cli/model-private-skill.py validate-input --input request.json
python cli/model-private-skill.py calculate --input request.json
python cli/model-private-skill.py gpu filter --min-vram-gb N --precision BF16 --max-results 5
python cli/model-private-skill.py validate-output result.json
```

如果宿主 Agent 不能执行本地 Python，不要手工伪造精确结果；说明运行能力缺失，并只提供待计算的规范化输入。

## 自动选型与确定性交付

hardware_profile 是可选字段。省略时，calculate 先输出每副本客观显存需求，并生成每档最多三个按单卡可用显存、TP/PP 对齐和节点边界计算的 GPU 组合；提供时，仅评估客户已有硬件。

完成资料核实后，必须按以下链路交付：

1. calculate 生成 calculation.json；
2. 将模型和框架的合格证据及框架结论写入 verified-enrichment.json；
3. build-plan 将两者组装为 schema 1.5 的 result.json；
4. validate-output 校验 result.json；
5. render-html 将已校验 result.json 生成独立 UTF-8 HTML。

框架必须引用已核实的引擎兼容性证据。render-html 拒绝渲染未通过 JSON 校验的计划。