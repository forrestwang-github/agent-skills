"""Turn objective per-replica memory requirements into GPU configurations."""

from __future__ import annotations

from datetime import date
import math
from typing import Any

from .capacity import align_parallelism, choose_topology, companion_resources
from .catalog import DEFAULT_CATALOG, load_catalog


def precision_feature(weight_bits: float) -> str:
    if weight_bits >= 16:
        return "BF16"
    if weight_bits >= 8:
        return "FP8"
    return "INT8"


def _requires_reverification(device: dict[str, Any], recheck_days: int) -> bool:
    if device["spec_status"] == "preliminary":
        return True
    try:
        return (date.today() - date.fromisoformat(device["source"]["accessed_at"])).days > recheck_days
    except (KeyError, TypeError, ValueError):
        return True


def select_gpu_configurations(
    calculation: dict[str, Any],
    request: dict[str, Any],
    *,
    max_results: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Return capacity-valid multi-card configurations for each tier."""
    catalog = load_catalog(DEFAULT_CATALOG)
    profile = request.get("hardware_profile") or {}
    max_gpus_per_node = profile.get("max_gpus_per_node", 8)
    parallel_degrees = profile.get(
        "supported_parallel_degrees", [1, 2, 4, 8, 16, 32, 64]
    )
    engineering = request.get("engineering") or {}
    workload = request["workload"]
    model = request["model"]
    response_mode = engineering.get("response_mode", "streaming")
    bytes_per_token = engineering.get("bytes_per_token", 4)
    protocol_overhead = engineering.get("protocol_overhead", 1.3)
    selection: dict[str, list[dict[str, Any]]] = {}

    for tier in ("economic", "peak_production"):
        tier_data = calculation["tiers"][tier]
        memory = tier_data["memory"]
        precision = precision_feature(request["precision"][tier + "_weight_bits"])
        required = memory["required_vram_per_replica_gb"]
        usable_ratio = memory["usable_vram_ratio"]
        replicas_by_performance = tier_data["gpu_capacity"].get("replicas_by_performance")
        minimum_replicas = 1 if tier == "economic" else 2
        replicas = max(minimum_replicas, replicas_by_performance or minimum_replicas)
        if tier == "peak_production" and engineering.get("failure_retains_full_peak"):
            replicas = max(2, (replicas_by_performance or 1) + 1)

        candidates: list[dict[str, Any]] = []
        for device in catalog["devices"]:
            if precision not in {value.upper() for value in device["precision_features"]}:
                continue
            usable_vram = device["memory_gb"] * usable_ratio
            by_memory = math.ceil(required / usable_vram)
            try:
                quantity = align_parallelism(by_memory, parallel_degrees)
            except ValueError:
                continue
            topology = choose_topology(quantity, max_gpus_per_node)
            scale_up = device["scale_up_interconnect"]
            if topology["tensor_parallel"] > 1 and scale_up is None:
                interconnect_note = "多卡 TP 仅有主机互联；必须用同条件压测确认。"
            elif topology["tensor_parallel"] > 1:
                interconnect_note = "需要核实 " + str(scale_up["name"]) + " 拓扑与框架支持。"
            else:
                interconnect_note = "单卡副本，无卡间并行依赖。"
            total_nodes = topology["nodes_per_replica"] * replicas
            resource = companion_resources(
                tier=tier,
                gpus_per_node=topology["gpus_per_node"],
                total_nodes=total_nodes,
                artifact_gb=model["artifact_gb"],
                public_arrival_rps=workload.get("typical_rps" if tier == "economic" else "peak_rps"),
                public_response_rps=workload.get("typical_response_rps" if tier == "economic" else "peak_response_rps"),
                response_mode=response_mode,
                active_concurrency=workload["typical_active_concurrency" if tier == "economic" else "peak_active_concurrency"],
                output_tps_per_request=(request.get("slo") or {}).get("output_tps_per_request"),
                input_tokens=workload["typical_input_tokens" if tier == "economic" else "max_input_tokens"],
                output_tokens=workload["typical_output_tokens" if tier == "economic" else "max_output_tokens"],
                bytes_per_token=bytes_per_token,
                protocol_overhead=protocol_overhead,
            )
            candidates.append({
                "catalog_id": device["id"], "vendor": device["vendor"],
                "model": device["model"], "form_factor": device["form_factor"],
                "vram_gb": device["memory_gb"],
                "usable_vram_per_gpu_gb": round(usable_vram, 3),
                "quantity_per_replica": quantity,
                "gpus_per_replica_by_memory": by_memory,
                "replicas": replicas, "total_gpus": quantity * replicas,
                "topology": {**topology, "data_parallel": replicas, "replicas": replicas},
                "node_configuration": {"total_nodes": total_nodes, **resource},
                "interconnect_note": interconnect_note,
                "requires_reverification": _requires_reverification(device, catalog["review_policy"]["final_spec_recheck_days"]),
                "source": {"publisher": device["vendor"], "title": device["source"]["title"], "url": device["source"]["url"], "published_at": device["source"]["published_at"], "accessed_at": device["source"]["accessed_at"]},
                "notes": device["notes"],
            })
        candidates.sort(key=lambda item: (item["total_gpus"], item["quantity_per_replica"], item["vram_gb"] * item["quantity_per_replica"] - required, -item["usable_vram_per_gpu_gb"], item["catalog_id"]))
        selection[tier] = candidates[:max_results]
    return selection
