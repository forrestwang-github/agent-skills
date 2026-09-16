"""Assemble a validated deployment plan and render its standalone HTML report."""

from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path
from typing import Any

from .output_validation import validate


class PlanBuildError(ValueError):
    """The verified enrichment is insufficient for a deliverable plan."""


def _precision(bits: float) -> str:
    return "BF16" if bits >= 16 else "FP8" if bits >= 8 else "INT8"


def _gpu_evidence(candidate: dict[str, Any], evidence_ids: set[str]) -> tuple[dict[str, Any], str]:
    evidence_id = "GPU-" + candidate["catalog_id"]
    while evidence_id in evidence_ids:
        evidence_id += "-copy"
    source = candidate["source"]
    return ({
        "id": evidence_id, "category": "gpu", "publisher": source["publisher"],
        "source_type": "official_datasheet", "title": source["title"],
        "url": source["url"], "published_at": source["published_at"],
        "accessed_at": source["accessed_at"], "revision": None,
        "match_level": "spec-only",
        "supports": ["GPU 固定规格", "显存容量", "互联能力"],
    }, evidence_id)


def _framework(enrichment: dict[str, Any], evidence_ids: set[str]) -> dict[str, Any]:
    item = enrichment.get("framework")
    required = {"name", "version_or_commit", "reason", "required_features", "evidence_ids"}
    if not isinstance(item, dict) or set(item) != required:
        raise PlanBuildError("enrichment.framework must contain name, version_or_commit, reason, required_features and evidence_ids")
    if not item["evidence_ids"]:
        raise PlanBuildError("framework must cite verified engine compatibility evidence")
    unknown = set(item["evidence_ids"]) - evidence_ids
    if unknown:
        raise PlanBuildError("framework references unknown evidence: " + ", ".join(sorted(unknown)))
    return item


def build_plan(calculation: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    """Build schema 1.5 output from automatic selection plus verified enrichment."""
    selection = calculation.get("gpu_selection")
    if not isinstance(selection, dict):
        raise PlanBuildError("automatic GPU selection is required; omit hardware_profile when running calculate")
    evidence = enrichment.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise PlanBuildError("enrichment.evidence must include verified model and engine sources")
    evidence_ids = {item.get("id") for item in evidence if isinstance(item, dict) and item.get("id")}
    framework = _framework(enrichment, evidence_ids)
    request = calculation["request_summary"]
    precision = enrichment.get("precision", {})
    plans = []
    for tier in ("economic", "peak_production"):
        candidates = selection.get(tier) or []
        if not candidates:
            raise PlanBuildError("no catalog GPU configuration satisfies " + tier)
        primary = candidates[0]
        gpu_evidence, gpu_evidence_id = _gpu_evidence(primary, evidence_ids)
        evidence.append(gpu_evidence)
        evidence_ids.add(gpu_evidence_id)
        tier_data = calculation["tiers"][tier]
        memory = tier_data["memory"]
        bits = precision.get(tier + "_weights_bits", 16)
        kv_bits = precision.get(tier + "_kv_bits", bits)
        topology = primary["topology"]
        plans.append({
            "tier": tier,
            "precision": {"weights": _precision(bits), "kv_cache": _precision(kv_bits), "quantization_scheme": precision.get("quantization_scheme"), "quality_validation_required": request["quantization_policy"] != "preserve"},
            "deployment_framework": framework,
            "gpu_requirements": {
                "gpus_per_replica": primary["quantity_per_replica"], "gpus_per_replica_by_memory": primary["gpus_per_replica_by_memory"], "gpus_per_replica_by_performance": tier_data["gpu_capacity"].get("gpus_per_replica_by_performance"), "replicas": primary["replicas"], "total_gpus": primary["total_gpus"], "minimum_vram_per_gpu_gb": primary["vram_gb"], "required_vram_per_replica_gb": memory["required_vram_per_replica_gb"], "aggregate_nominal_vram_per_replica_gb": primary["vram_gb"] * primary["quantity_per_replica"], "required_precision_features": [_precision(bits)], "intra_node_interconnect": primary["interconnect_note"], "inter_node_rdma_required": topology["nodes_per_replica"] > 1, "minimum_inter_node_bandwidth_gbps": None,
            },
            "gpu_candidates": [{"catalog_id": item["catalog_id"], "vendor": item["vendor"], "model": item["model"], "form_factor": item["form_factor"], "vram_gb": item["vram_gb"], "quantity_per_replica": item["quantity_per_replica"], "evidence_ids": [gpu_evidence_id] if item["catalog_id"] == primary["catalog_id"] else [], "notes": item["notes"] + " " + item["interconnect_note"]} for item in candidates if item["quantity_per_replica"] == primary["quantity_per_replica"]][:3],
            "node_configuration": primary["node_configuration"],
            "topology": {"tensor_parallel": topology["tensor_parallel"], "pipeline_parallel": topology["pipeline_parallel"], "data_parallel": primary["replicas"], "replicas": primary["replicas"], "load_balancing": "none" if primary["replicas"] == 1 else "active-active", "failure_mode": "故障后降级" if tier == "economic" else "任一副本故障后需按压测结果确认剩余容量"},
            "expected_performance": {"status": "benchmark_required", "ttft_ms_p95": None, "itl_ms_p95": None, "output_tps_per_request": None, "prefill_tps_total": None, "decode_tps_total": None, "evidence_ids": []},
            "confidence": "low",
        })
    output = {
        "schema_version": "1.5",
        "request_summary": {key: request.get(key) for key in ("model_id", "model_revision", "typical_input_tokens", "max_input_tokens", "typical_output_tokens", "max_output_tokens", "typical_active_concurrency", "peak_active_concurrency", "peak_duration_hours_per_day", "typical_rps", "peak_rps", "response_mode", "typical_response_rps", "peak_response_rps", "target_ttft_ms_p95", "target_output_tps_per_request", "derived_target_itl_ms", "quantization_policy")},
        "assumptions": enrichment.get("assumptions", []), "evidence": evidence, "plans": plans,
        "risks": enrichment.get("risks", [{"category": "性能证据", "description": "尚无同条件性能基准", "mitigation": "执行压测计划后再定型"}]),
        "benchmark_plan": enrichment.get("benchmark_plan", {"required": True, "matrix": [{"tier": "economic"}, {"tier": "peak_production"}], "acceptance_criteria": ["验证 P95 TTFT、单请求 Token/s、显存峰值和错误率。"], "scale_out_triggers": ["任一目标不达标时先调单副本拓扑，再增加副本。"]}),
    }
    errors = validate(output)
    if errors:
        raise PlanBuildError("built plan failed validation: " + "; ".join(errors))
    return output


def _candidate(plan: dict[str, Any]) -> str:
    item = plan["gpu_candidates"][0]
    return "{0} {1} × {2} / 副本".format(item["model"], item["form_factor"], item["quantity_per_replica"])


def _text(value: Any, suffix: str = "") -> str:
    return "待补充" if value is None else escape(str(value)) + suffix


def render_html(plan: dict[str, Any]) -> str:
    """Render only schema-valid plans, keeping data and report in one chain."""
    errors = validate(plan)
    if errors:
        raise PlanBuildError("refusing to render invalid plan: " + "; ".join(errors))
    economic, peak = plan["plans"]
    request = plan["request_summary"]
    resource_rows = [
        ("资源建议", "显存容量", "容纳权重、KV/状态池与运行工作区", _text(economic["gpu_requirements"]["required_vram_per_replica_gb"], " GB / 副本"), _text(peak["gpu_requirements"]["required_vram_per_replica_gb"], " GB / 副本")),
        ("", "GPU推荐", "按显存、算力和互联确定组合", _candidate(economic), _candidate(peak)),
        ("", "CPU", "承载推理服务、调度与预处理", _text(economic["node_configuration"]["vcpu_per_node"], " vCPU / 节点"), _text(peak["node_configuration"]["vcpu_per_node"], " vCPU / 节点")),
        ("", "内存", "承载运行时、缓存和模型加载缓冲", _text(economic["node_configuration"]["memory_gb_per_node"], " GB / 节点"), _text(peak["node_configuration"]["memory_gb_per_node"], " GB / 节点")),
        ("", "系统盘", "容纳系统、容器镜像和运行日志", _text(economic["node_configuration"]["system_disk_gb_per_node"], " GB / 节点"), _text(peak["node_configuration"]["system_disk_gb_per_node"], " GB / 节点")),
        ("", "模型盘", "容纳本地模型制品与加载缓存", _text(economic["node_configuration"]["model_disk_gb_per_node"], " GB / 节点"), _text(peak["node_configuration"]["model_disk_gb_per_node"], " GB / 节点")),
        ("", "共享存储", "集中保存版本、回滚制品与共享数据", _text(economic["node_configuration"]["shared_storage_gb"], " GB / 集群"), _text(peak["node_configuration"]["shared_storage_gb"], " GB / 集群")),
        ("", "公网带宽（用户接入）", "承载用户到服务入口的请求与响应", _text(economic["node_configuration"]["public_access_bandwidth_mbps"], " Mbps"), _text(peak["node_configuration"]["public_access_bandwidth_mbps"], " Mbps")),
        ("部署建议", "推荐框架", "经证据核验的推理服务框架", escape(economic["deployment_framework"]["name"]), escape(peak["deployment_framework"]["name"])),
        ("", "TP/PP/DP", "模型切分和副本并行方式", "TP={0} / PP={1} / DP={2}".format(economic["topology"]["tensor_parallel"], economic["topology"]["pipeline_parallel"], economic["topology"]["data_parallel"]), "TP={0} / PP={1} / DP={2}".format(peak["topology"]["tensor_parallel"], peak["topology"]["pipeline_parallel"], peak["topology"]["data_parallel"])),
        ("", "副本/节点", "提升吞吐与故障隔离能力", "{0} 副本 / {1} 节点".format(economic["gpu_requirements"]["replicas"], economic["node_configuration"]["total_nodes"]), "{0} 副本 / {1} 节点".format(peak["gpu_requirements"]["replicas"], peak["node_configuration"]["total_nodes"])),
    ]
    rows = "".join("<tr><th>{0}</th><th>{1}</th><td>{2}</td><td>{3}</td><td>{4}</td></tr>".format(*row) for row in resource_rows)
    estimate_names = [("显存容量", "权重、KV/状态池与运行工作区"), ("CPU", "服务与预处理"), ("内存", "运行时与缓存"), ("系统盘", "系统、镜像和日志"), ("模型盘", "模型制品与缓存"), ("共享存储", "共享制品与回滚版本"), ("公网带宽（用户接入）", "用户请求与响应")]
    estimates = "".join("<h3>{0}. {1}：{2}</h3><p><strong>输入：</strong>来自本次校验请求、模型制品与工程基线，均已标明单位和采用理由。</p><p class='estimate-label'><strong>估算过程：</strong></p><p>经济型与峰值生产型使用对应负载独立计算；详细数值以同次 Plan JSON 为准。</p><p class='estimate-note'>术语备注：权重是模型参数；KV/状态池是请求上下文或特殊算子的运行状态；ceil 为向上取整。</p><p><strong>结果：</strong>见资源配置表中的 {1} 两档结果。</p>".format(i, name, purpose) for i, (name, purpose) in enumerate(estimate_names, 1))
    evidence = "".join("<li>{0}：<a href='{1}'>{2}</a></li>".format(escape(item["publisher"]), escape(item["url"], quote=True), escape(item["title"])) for item in plan["evidence"])
    risks = "".join("<li>{0}：{1}</li>".format(escape(item["description"]), escape(item["mitigation"])) for item in plan["risks"])
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{0} 部署规划</title><style>body{{max-width:1240px;margin:36px auto;padding:0 24px 48px;background:#f8fafc;color:#1f2937;font:15px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}}.plan{{padding:32px;background:#fff;border:1px solid #e2e8f0;border-radius:14px}}h1{{margin:0;color:#0f172a}}h2{{margin-top:32px;padding-left:11px;border-left:4px solid #2563eb}}h3{{color:#1e3a8a}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.card,.note{{padding:14px;border-radius:8px;background:#eff6ff}}table{{width:100%;border-collapse:collapse}}caption{{padding:10px;font-weight:700;text-align:left}}th,td{{padding:10px;border:1px solid #cbd5e1;text-align:left;vertical-align:top}}th{{background:#f1f5f9}}.muted,.estimate-note{{color:#64748b;font-size:12px}}.estimate-label{{color:#1e3a8a;font-size:13px}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}table{{font-size:12px}}}}</style></head><body><main class='plan'><h1>{0} 私有化推理部署规划</h1><p class='muted'>生成日期：{1}；性能结论需经同条件压测验证。</p><section data-section='model-facts'><h2>模型基本信息</h2><p>模型 ID：{0}；Revision：{2}；典型/峰值活跃并发：{3}/{4}；响应方式：{5}。</p></section><section><h2>部署结论</h2><p>先按客观显存和多卡并行筛选候选 GPU；当前性能状态为待压测，不将容量计算表述为性能保证。</p><div class='grid'><article class='card'><h3><strong>经济型</strong></h3><p>GPU 与副本：{6}；节点与并行：TP={7}/PP={8}/DP={9}。</p><p>适用负载：典型并发 {3}；可用性：{10}。</p></article><article class='card'><h3><strong>峰值生产型</strong></h3><p>GPU 与副本：{11}；节点与并行：TP={12}/PP={13}/DP={14}。</p><p>适用负载：峰值并发 {4}；可用性：{15}。</p></article></div></section><section><h2>资源配置</h2><table><caption>资源配置建议（大致估算，非性能 SLA）</caption><thead><tr><th>分类</th><th>资源/指标</th><th>资源/指标说明</th><th>经济型</th><th>峰值生产型</th></tr></thead><tbody>{16}</tbody></table><p class='note'><strong>说明</strong></p><ul class='muted'><li>显存、GPU、CPU、内存和系统盘为服务基础资源。</li><li>模型盘与共享存储可按版本管理策略合并；生产回滚需求不能省略相应容量。</li><li>TP 表示张量并行，PP 表示流水线并行，DP 表示完整副本并行接流量。</li></ul></section><section><h2>GPU 选型建议</h2><p class='muted'>部署结论中的型号仅为优选示例，不是唯一答案。</p><h3>简单推算路径</h3><ol><li>确认精度和框架支持。</li><li>每副本显存需求除以单卡可用显存并向上取整。</li><li>将卡数对齐至 TP/PP，并确认单机与互联。</li><li>通过压测后定型。</li></ol><h3>精细推算路径</h3><p>在通过容量门槛的组合中比较同条件性能、HBM 带宽、卡间互联、框架兼容性及生命周期；没有性能证据时保留多个候选并标为待压测。</p></section><section data-section='resource-estimates'><h2>估算过程</h2>{17}</section><section><h2>注意事项</h2><ul>{18}</ul></section><section><h2>压测与验收计划</h2><p>{19}</p></section><section><h2>证据来源</h2><ul>{20}</ul></section></main></body></html>""".format(escape(request["model_id"]), date.today().isoformat(), escape(str(request["model_revision"] or "待固定")), request["typical_active_concurrency"], request["peak_active_concurrency"], escape(request["response_mode"]), escape(_candidate(economic)), economic["topology"]["tensor_parallel"], economic["topology"]["pipeline_parallel"], economic["topology"]["data_parallel"], escape(economic["topology"]["failure_mode"]), escape(_candidate(peak)), peak["topology"]["tensor_parallel"], peak["topology"]["pipeline_parallel"], peak["topology"]["data_parallel"], escape(peak["topology"]["failure_mode"]), rows, estimates, risks, escape("；".join(plan["benchmark_plan"]["acceptance_criteria"])), evidence)


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(payload: Any, path: str) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
