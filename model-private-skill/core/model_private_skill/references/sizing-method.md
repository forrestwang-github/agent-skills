# 平台无关容量计算方法

## 目录

- [单位与负载标准化](#单位与负载标准化)
- [显存约束](#显存约束)
- [性能约束](#性能约束)
- [并行与副本](#并行与副本)
- [配套资源](#配套资源)
- [置信度](#置信度)

## 单位与负载标准化

容量统一使用十进制 GB，公网用户接入带宽明确 Mbps/Gbps，时间统一 ms。

RPS 缺失时：

```text
request_duration_seconds =
  target_ttft_seconds
  + typical_output_tokens / target_output_tps_per_request

estimated_rps =
  active_concurrency / request_duration_seconds
```

计算典型与峰值 Decode：

```text
typical_decode_tps = max(
  typical_active_concurrency × target_output_tps_per_request,
  typical_rps × typical_output_tokens
)

peak_decode_tps = max(
  peak_active_concurrency × target_output_tps_per_request,
  peak_rps × typical_output_tokens
)
```

计算 Prefill：

```text
typical_prefill_tps = typical_rps × typical_input_tokens
peak_prefill_tps = peak_rps × typical_input_tokens
```

峰值闲置参考：

```text
daily_equivalent_concurrency =
  (
    typical_active_concurrency × (24 - peak_duration_hours_per_day)
    + peak_active_concurrency × peak_duration_hours_per_day
  ) / 24
```

该值只解释峰值容量的平均需求代理，不得写成实际 GPU 利用率，也不得据此削减峰值保障方案。

## 显存约束

优先使用精确 revision 的实际模型制品及引擎加载测量。

普通权重估算：

```text
weight_gb = total_resident_parameters × weight_bits / 8 / 1e9
```

MoE 必须用总驻留参数计算权重；激活参数仅用于计算量和性能判断。

普通 Transformer KV cache：

```text
kv_bytes_per_token =
  2 × layers × kv_heads × head_dim × kv_bits / 8

kv_cache_gb =
  kv_bytes_per_token × live_tokens / 1e9
```

典型与峰值 live tokens：

```text
typical_live_tokens =
  typical_active_concurrency
  × (typical_input_tokens + typical_output_tokens)

peak_expected_live_tokens =
  peak_active_concurrency
  × (typical_input_tokens + typical_output_tokens)
```

另算最大长度安全范围：

```text
max_live_tokens =
  max_length_concurrency
  × (max_input_tokens + max_output_tokens)
```

若 `max_length_concurrency` 未知，使用 1 到峰值并发形成上下界。若上下界跨越 GPU 卡数边界，必须追问，不得选择其中一个伪装成精确结果。

MLA、CSA、HCA、滑动窗口或压缩 KV 等特殊注意力不得直接使用通用公式。使用以下任一依据：

1. 模型官方公式；
2. 推理引擎对应实现文档；
3. 相同 revision、精度和上下文下的运行时显存测量；
4. 用户提供的 `kv_bytes_per_token` 实测值。

工作区与总显存：

```text
workspace_gb = (weight_gb + kv_cache_gb) × 0.20
required_vram_per_replica_gb =
  weight_gb + kv_cache_gb + workspace_gb
```

- `economic`：使用典型 live tokens，有效显存比例 90%。
- `peak_production`：使用峰值预期 live tokens，并用最大长度安全范围复核；有效显存比例 85%。

```text
gpus_by_memory =
  ceil(required_vram_per_replica_gb / usable_vram_per_gpu_gb)
```

分别按两档实际精度计算，禁止用同一个权重位宽代表两档。

## 性能约束

基准必须绑定：

- 模型 revision、权重/KV 精度；
- 引擎及版本；
- GPU 精确型号、形态和数量；
- TP、PP、DP；
- 输入/输出长度、并发、RPS；
- batching/token budget、Prefix Cache 和 Speculative Decoding。

匹配等级：

- `exact`：关键条件一致，可输出已验证结论。
- `similar`：部分条件不同，只输出估算区间。
- `spec-only`：只有模型或硬件规格，性能值必须为 `null`。

有可用基准时：

```text
replicas_by_performance = max(
  ceil(required_prefill_tps / benchmark_prefill_tps_per_replica),
  ceil(required_decode_tps / benchmark_decode_tps_per_replica)
)
```

若单请求 TTFT/Token/s 不能由该副本拓扑满足，先增加单副本 GPU/调整并行度，再计算副本数。不得只用更多副本掩盖单请求 SLO 不达标。

没有 exact 或可解释的 similar 基准时：

- GPU 数只表示显存容量下限；
- TTFT、ITL、Token/s、吞吐均设为 `null`；
- `expected_performance.status = benchmark_required`；
- 给出压测矩阵、验收项和扩容触发条件。

## 并行与副本

拓扑选择顺序：

1. 单卡容纳时优先 `TP=1, PP=1`。
2. 单卡不能容纳时增加 TP，优先单节点 NVLink/NVSwitch 或厂商等价互联。
3. 单节点不能容纳时才使用 PP 或有官方依据的跨节点 TP。
4. 单副本拓扑确定后，通过独立副本扩展总吞吐和可用性。

```text
gpus_per_replica =
  align_supported_parallelism(
    max(gpus_by_memory, gpus_by_single_request_performance)
  )

gpus_per_replica ≈ TP × PP
total_gpus = gpus_per_replica × replicas
```

副本数：

```text
economic_replicas =
  max(1, typical_replicas_by_performance)

peak_production_replicas =
  max(2, peak_replicas_by_performance)
```

`DP` 表示可并行接流量的完整模型副本数，通常等于 replicas。生产方案默认双副本分担峰值；用户明确要求故障后仍满足完整峰值时，每个副本都按完整峰值计算。

## 配套资源

优先使用模型或推理引擎官方建议。缺失时使用并标注工程基线。

每节点 CPU：

```text
economic_vcpu = max(16, 8 × gpus_per_node)
peak_production_vcpu = max(32, 16 × gpus_per_node)
```

每节点主机内存：

```text
economic_memory_gb =
  max(128, ceil(model_artifact_gb × 1.25))

peak_production_memory_gb =
  max(256, ceil(model_artifact_gb × 1.50))
```

CPU Offload、多模态预处理、大量 LoRA 或复杂 Tokenization 必须额外评估。

存储使用实际模型制品：

- `economic` 系统盘 100 GB；模型盘 `ceil(artifact × 1.2)`，保存 1 个版本。
- `peak_production` 系统盘 200 GB；模型盘 `ceil(artifact × 2 × 1.2)`，保存当前和回滚版本。
- 共享存储与本地模型盘分列；共享存储按集群实际版本策略计算，不按节点重复累加。

公网用户接入带宽：

输入与输出载荷：

input_payload_bytes_per_request =
  planned_input_tokens × average_bytes_per_token

output_payload_bytes_per_request =
  planned_output_tokens × average_bytes_per_token

计算分支：

public_access_ingress_peak_bps =
  user_supplied_arrival_rps × input_payload_bytes_per_request × 8 × protocol_overhead

流式输出（SSE/WebSocket 等）：
public_access_egress_peak_bps =
  active_streaming_concurrency × target_output_tps_per_request
  × average_bytes_per_token × 8 × protocol_overhead

非流式输出（完整结果缓冲后一次或短窗口返回）：
public_access_egress_peak_bps =
  user_supplied_response_completion_rps × output_payload_bytes_per_request
  × 8 × protocol_overhead

public_access_peak_bps =
  max(public_access_ingress_peak_bps, public_access_egress_peak_bps)

默认 average_bytes_per_token=4、protocol_overhead=1.3，均标记为假设；协议系数应覆盖 JSON、TLS，以及流式场景的 SSE/WebSocket 事件封装与心跳。economic 使用典型长度和典型负载，peak_production 使用最大长度和峰值负载。公网入向只接受用户提供的典型/峰值到达 RPS：由并发和请求时长反推的 RPS 仅能作为推理容量代理，不能作为公网突发到达率。流式出向按同时活跃流和每流输出 Token/s 计算；非流式出向必须使用用户提供的典型/峰值响应完成 RPS。任一适用方向缺少真实 RPS 或输出速度时，最终公网带宽为 null 并列为待补充，不以并发或平均时长补齐。入向、出向与最终峰值结果均直接保留到 0.001 Mbps；不设置 1 Gbps 或其他人为下限。
本公式仅估算公网用户接入带宽，即用户到 API 网关或服务入口的南北向请求与响应。在实际部署中，还应注意：服务私网带宽用于网关、推理副本、存储等内部东西向通信，按部署拓扑单独核实；若同一推理副本采用跨节点 TP/PP，还需单独评估低时延高速互联与 RDMA 网络。节点内互联、服务私网与跨节点 GPU 网络均不纳入本公式；跨节点 TP/PP 仅在官方或同条件实测支持时填写具体 RDMA 最低带宽，否则为 `null` 并标记待压测。

## 置信度

- `high`：模型、GPU、引擎可核实，且存在 exact 性能基准。
- `medium`：规格可核实，性能来自 similar 基准或有限外推。
- `low`：模型结构、精度/算子兼容性、请求分布或性能证据存在关键缺口。

`medium` 和 `low` 必须输出压测矩阵、验收标准和扩容触发条件。
