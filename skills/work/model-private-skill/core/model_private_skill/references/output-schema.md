# 平台无关输出格式与 JSON 1.5 契约

## 目录

- [默认正文](#默认正文)
- [HTML 固定格式](#html-固定格式)
- [JSON 规则](#json-规则)
- [request_summary](#request_summary)
- [assumptions 与 evidence](#assumptions-与-evidence)
- [plans](#plans)
- [risks 与 benchmark_plan](#risks-与-benchmark_plan)
- [一致性校验](#一致性校验)

## 默认正文

用户可见交付物必须写入一个可直接打开的 UTF-8 HTML 文件，并严格按 [HTML 输出模板](html-output-template.md) 组织。文件名使用 <规范化模型-id>-deployment-plan.html；最终回复提供文件链接：

1. 标题后首先输出模型基本信息，说明制品/revision、参数和架构、模态、上下文、权重或制品大小、注意力/特殊算子和部署限制；
2. 部署结论先给一句话结论，再并排展示经济型与峰值生产型；两档均按 GPU 与副本、节点与并行、适用负载、可用性、性能目标独立成行；
3. 资源配置使用固定五列表格：分类、资源/指标、资源/指标说明、经济型、峰值生产型。资源/指标说明不超过 30 个汉字；
4. 默认规划值在表内规划基线分档呈现，包括活跃并发、输入/输出长度、最大长度同时并发、性能目标和输入形态；最大长度同时并发是同时执行最大长度请求数；
5. 显存容量是资源建议第一行且单独展示，只写每推理副本的客观显存需求，不得出现任何具体 GPU 型号；GPU推荐紧随显存容量之后，副本/节点是部署建议最后一行；不展示性能状态；
6. 业务场景与能力差异只用一行，经济型与峰值生产型内容分别落在两列，写明并发、可用性、TTFT/Token/s 与故障影响，并注明大致估算，非 SLA；
7. 表格下方以分条“说明”写明：必备资源、可按负载酌情下调的资源、可合并资源，以及 TP/PP/DP 的简要释义；
8. 表格下方固定输出 GPU 选型建议，随后输出估算过程；GPU 章节开头说明部署结论和 GPU推荐中的型号仅为优选示例，随后分为两条路径：简单推算按精度/软件、显存、并行、压测快速筛选；精细推算按容量、并行与互联、性能、工程与生命周期逐层比较。具体型号只作满足条件后的示例候选，不输出复杂候选池；
9. 估算过程仅按资源建议的七类资源展开：显存容量、CPU、内存、系统盘、模型盘、共享存储、公网带宽（用户接入）。每个标题固定使用“序号 + 资源名：用途”；每项按输入、估算过程、术语备注、结果说明。术语备注以小字号解释该项使用的专有名词或函数；公式中出现的每一个数值必须在输入中标明数值、单位、来源或采用理由，不能保留未解释的常量。公网带宽的入向只使用用户实测到达 RPS；流式出向使用活跃流并发和单请求 Token/s，非流式出向使用用户实测响应完成 RPS；不得将并发和请求时长反推值用于公网突发带宽。任一适用方向缺少真实输入时最终带宽为 null。公网带宽的输入下须以“在实际部署中，还应注意”说明服务私网和跨节点 GPU 网络按拓扑单独核实；分别直接输出峰值入向、峰值出向和二者较大值，不设置人为下限。结果直接陈述，不写“与表格对应”；GPU 型号、框架、并行和副本不在本节重复估算；
10. 最后输出部署注意事项、压测与验收计划、未决信息和证据来源。模型出现混合注意力或特殊算子时，必须在模型基本信息首次出现处以小字号说明其作用、资源/兼容性影响和部署决策；注意事项说明规划成立边界和重评估触发条件；压测与验收计划说明测试矩阵、验收指标及未达标后的调整路径；文档包含 doctype、lang、UTF-8、viewport、title、内嵌 CSS 与 main.plan 容器。

HTML 表格至少包含：规划基线、显存容量、精度、CPU、内存、系统盘、模型盘、共享存储、公网带宽（用户接入）、TP/PP/DP、推荐框架、业务场景与能力差异、GPU、副本/节点。JSON 仍可作为机器接口附带输出，但不替代 HTML；JSON 中的 expected_performance.status 只用于机器校验，不显示在 HTML 资源配置表中。
## HTML 固定格式

HTML 模板位于 [html-output-template.md](html-output-template.md)。必须生成该模板规定的独立 HTML 文件，不得改回 Markdown、聊天片段或自由发挥章节顺序；内嵌 CSS、类名和移动端表格行为均为固定要求。

## JSON 规则

- 输出合法 JSON，不添加注释。
- schema_version 固定为 1.5。
- 每个方案必须包含 `deployment_framework`，写明推荐框架、版本/commit（能核实时）、选择理由、必需特性和证据 ID。
- 顶层只能包含：
  - `schema_version`
  - `request_summary`
  - `assumptions`
  - `evidence`
  - `plans`
  - `risks`
  - `benchmark_plan`
- `plans` 按 `economic`、`peak_production` 顺序包含两个对象。
- 未知数值使用 `null`，不使用“未知”“约”等字符串代替数值。
- 日期使用 `YYYY-MM-DD`；容量为十进制 GB；公网用户接入带宽字段注明 Mbps/Gbps。
- 表格与 JSON 必须由同一次计算结果生成。
- 不出现云厂商实例 SKU、区域、库存、价格、折扣、报价、采购或禁售字段。
- 保存 JSON 后运行 `model-private-skill validate-output result.json`；校验失败时先修正再交付。
- 机器接口的 JSON Schema 位于同一核心包的 `schemas/output-schema.json`；运行时通常只执行校验命令，不把整个 Schema 加载进上下文。

## request_summary

固定字段：

| 字段 | 类型 |
|---|---|
| model_id | string |
| model_revision | string 或 null |
| typical_input_tokens | integer 或 null |
| max_input_tokens | integer 或 null |
| typical_output_tokens | integer 或 null |
| max_output_tokens | integer 或 null |
| typical_active_concurrency | integer 或 null |
| peak_active_concurrency | integer 或 null |
| peak_duration_hours_per_day | number 或 null |
| typical_rps | number 或 null；推理容量可由并发代理，但公网入向只能采用用户实测值 |
| peak_rps | number 或 null；推理容量可由并发代理，但公网入向只能采用用户实测值 |
| response_mode | string：streaming 或 non_streaming |
| typical_response_rps | number 或 null；非流式典型响应完成速率 |
| peak_response_rps | number 或 null；非流式峰值响应完成速率 |
| target_ttft_ms_p95 | number 或 null |
| target_output_tps_per_request | number 或 null |
| derived_target_itl_ms | number 或 null |
| quantization_policy | string：preserve、validated_only 或 cost_first |

## assumptions 与 evidence

`assumptions[]`：

- `item`：假设项；
- `value`：采用值；
- `impact`：对卡数、拓扑或性能的影响。

外部核实事实不得放入 assumptions。

`evidence[]`：

- `id`：唯一 ID，例如 `E1`；
- `category`：`model`、`gpu`、`engine` 或 `benchmark`；
- `publisher`：实际发布组织；
- `source_type`：`official_artifact`、`official_documentation`、`official_repository`、`official_datasheet`、`official_benchmark`、`reproducible_benchmark` 或 `user_supplied`；
- `title`：原始资料标题；
- `url`：直接来源 URL；
- `published_at`：发布日期或 `null`；
- `accessed_at`：访问日期；
- `revision`：模型 commit、文档版本或 `null`；
- `match_level`：`exact`、`similar` 或 `spec-only`；
- `supports`：该证据支持的结论数组。

每个 GPU 候选和性能结论必须关联存在的证据 ID。
来源必须通过[证据来源策略](source-policy.md)准入；搜索摘要、聚合页和第三方转述不得进入 `evidence[]`。

## plans

每个对象必须包含：

- `tier`
- `precision`
- `gpu_requirements`
- `gpu_candidates`
- `node_configuration`
- `topology`
- `expected_performance`
- `confidence`
- `deployment_framework`

### deployment_framework

| 字段 | 类型 |
|---|---|
| name | string |
| version_or_commit | string 或 null |
| reason | string |
| required_features | array of string |
| evidence_ids | array of string |

`name` 是最终推荐的推理框架，例如 vLLM、SGLang 或 TensorRT-LLM；不能只写“自动选择”。如果没有官方兼容性或性能证据，明确写出限制并保留压测要求。

### precision

| 字段 | 类型 |
|---|---|
| weights | string |
| kv_cache | string |
| quantization_scheme | string 或 null |
| quality_validation_required | boolean |

### gpu_requirements

| 字段 | 类型 |
|---|---|
| gpus_per_replica | integer |
| gpus_per_replica_by_memory | integer |
| gpus_per_replica_by_performance | integer 或 null |
| replicas | integer |
| total_gpus | integer |
| minimum_vram_per_gpu_gb | number |
| required_vram_per_replica_gb | number |
| aggregate_nominal_vram_per_replica_gb | number |
| required_precision_features | array of string |
| intra_node_interconnect | string |
| inter_node_rdma_required | boolean |
| minimum_inter_node_bandwidth_gbps | number 或 null |

`gpus_per_replica_by_performance=null` 表示没有足够性能基准；此时 `gpus_per_replica` 只是显存与并行度下限。

### gpu_candidates

每项包含：

- `catalog_id`
- `vendor`
- `model`
- `form_factor`
- `vram_gb`
- `quantity_per_replica`
- `evidence_ids`
- `notes`

每档最多 3 项，且 `quantity_per_replica` 必须等于该方案的 `gpus_per_replica`。

### node_configuration

| 字段 | 类型 |
|---|---|
| gpus_per_node | integer |
| nodes_per_replica | integer |
| total_nodes | integer |
| vcpu_per_node | integer |
| total_vcpu | integer |
| memory_gb_per_node | integer |
| total_memory_gb | integer |
| system_disk_gb_per_node | integer |
| total_system_disk_gb | integer |
| model_disk_gb_per_node | integer |
| total_model_disk_gb | integer |
| shared_storage_gb | integer |
| public_access_ingress_peak_mbps | number 或 null；只按用户实测到达 RPS 计算 |
| public_access_egress_peak_mbps | number 或 null；流式按活跃流与 Token/s，非流式按响应完成 RPS |
| public_access_bandwidth_mbps | number 或 null；两方向输入齐全时取入向/出向峰值的较大值 |
| public_access_response_mode | string：streaming 或 non_streaming |

### topology

- `tensor_parallel`：integer；
- `pipeline_parallel`：integer；
- `data_parallel`：integer；
- `replicas`：integer；
- `load_balancing`：`none` 或 `active-active`；
- `failure_mode`：文字说明单副本故障后的容量变化。

### expected_performance

| 字段 | 类型 |
|---|---|
| status | verified、estimated 或 benchmark_required |
| ttft_ms_p95 | number 或 null |
| itl_ms_p95 | number 或 null |
| output_tps_per_request | number 或 null |
| prefill_tps_total | number 或 null |
| decode_tps_total | number 或 null |
| evidence_ids | array of string |

当 `status=benchmark_required` 时，所有实测性能数值必须为 `null`。

`confidence` 固定为 `high`、`medium` 或 `low`。

## risks 与 benchmark_plan

`risks[]` 每项包含：

- `category`
- `description`
- `mitigation`

`benchmark_plan`：

- `required`：boolean；
- `matrix`：测试场景数组，至少覆盖典型、峰值和最大长度安全场景；
- `acceptance_criteria`：覆盖 P95 TTFT、单请求 Token/s/ITL、Prefill/Decode 吞吐、峰值显存、错误率和稳定运行时间；
- `scale_out_triggers`：达到何种利用率、排队、延迟或错误率后扩容。

## 一致性校验

- `economic.replicas >= 1`。
- `peak_production.replicas >= 2`，且为独立副本。
- `total_gpus = gpus_per_replica × replicas`。
- `nodes_per_replica = ceil(gpus_per_replica / gpus_per_node)`。
- `total_nodes = nodes_per_replica × replicas`。
- `total_vcpu = vcpu_per_node × total_nodes`。
- `total_memory_gb = memory_gb_per_node × total_nodes`。
- 本地磁盘总量等于每节点磁盘乘总节点数；共享存储不重复乘节点。
- 每个候选数量与方案拓扑一致。
- 所有 `evidence_id` 均可解析。
- MoE 权重计算使用总驻留参数。
- 表格与 JSON 数值一致。
