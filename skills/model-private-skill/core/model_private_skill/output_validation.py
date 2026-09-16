#!/usr/bin/env python3
"""Validate platform-neutral schema 1.5 output and arithmetic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


TOP_LEVEL_KEYS = {
    "schema_version",
    "request_summary",
    "assumptions",
    "evidence",
    "plans",
    "risks",
    "benchmark_plan",
}
REQUEST_KEYS = {
    "model_id",
    "model_revision",
    "typical_input_tokens",
    "max_input_tokens",
    "typical_output_tokens",
    "max_output_tokens",
    "typical_active_concurrency",
    "peak_active_concurrency",
    "peak_duration_hours_per_day",
    "typical_rps",
    "peak_rps",
    "response_mode",
    "typical_response_rps",
    "peak_response_rps",
    "target_ttft_ms_p95",
    "target_output_tps_per_request",
    "derived_target_itl_ms",
    "quantization_policy",
}
PLAN_KEYS = {
    "tier",
    "precision",
    "deployment_framework",
    "gpu_requirements",
    "gpu_candidates",
    "node_configuration",
    "topology",
    "expected_performance",
    "confidence",
}
FORBIDDEN_KEYS = {
    "cloud_provider",
    "cloud_instance",
    "cloud_instance_sku",
    "instance_sku",
    "region",
    "availability_zone",
    "inventory",
    "stock",
    "price",
    "quote",
    "discount",
    "purchase",
    "purchase_path",
    "sales_status",
    "export_status",
}
FRAMEWORK_KEYS = {
    "name",
    "version_or_commit",
    "reason",
    "required_features",
    "evidence_ids",
}
EVIDENCE_KEYS = {
    "id",
    "category",
    "publisher",
    "source_type",
    "title",
    "url",
    "published_at",
    "accessed_at",
    "revision",
    "match_level",
    "supports",
}
EVIDENCE_SOURCE_TYPES = {
    "official_artifact",
    "official_documentation",
    "official_repository",
    "official_datasheet",
    "official_benchmark",
    "reproducible_benchmark",
    "user_supplied",
}
SOURCE_TYPES_BY_CATEGORY = {
    "model": {
        "official_artifact",
        "official_documentation",
        "official_repository",
        "user_supplied",
    },
    "gpu": {
        "official_documentation",
        "official_repository",
        "official_datasheet",
        "user_supplied",
    },
    "engine": {
        "official_documentation",
        "official_repository",
        "user_supplied",
    },
    "benchmark": {
        "official_benchmark",
        "reproducible_benchmark",
        "user_supplied",
    },
}


def walk_keys(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append((path, key))
            found.extend(walk_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_keys(item, f"{path}[{index}]"))
    return found


def require_keys(
    errors: list[str], value: Any, required: set[str], path: str, exact: bool = False
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return
    missing = required - set(value)
    if missing:
        errors.append(f"{path} missing keys: {sorted(missing)}")
    if exact:
        extra = set(value) - required
        if extra:
            errors.append(f"{path} has unsupported keys: {sorted(extra)}")


def validate_plan(
    plan: Any, expected_tier: str, evidence_ids: set[str], errors: list[str]
) -> None:
    path = f"plans[{expected_tier}]"
    require_keys(errors, plan, PLAN_KEYS, path, exact=True)
    if not isinstance(plan, dict):
        return
    if plan.get("tier") != expected_tier:
        errors.append(f"{path}.tier must be {expected_tier}")
    if plan.get("confidence") not in ("high", "medium", "low"):
        errors.append(f"{path}.confidence must be high, medium or low")

    framework = plan.get("deployment_framework")
    if not isinstance(framework, dict):
        errors.append(f"{path}.deployment_framework must be an object")
    else:
        require_keys(errors, framework, FRAMEWORK_KEYS, f"{path}.deployment_framework", exact=True)
        if not isinstance(framework.get("name"), str) or not framework["name"].strip():
            errors.append(f"{path}.deployment_framework.name must be non-empty")
        if not isinstance(framework.get("reason"), str) or not framework["reason"].strip():
            errors.append(f"{path}.deployment_framework.reason must be non-empty")
        for evidence_id in framework.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"{path} references missing evidence {evidence_id}")

    gpu = plan.get("gpu_requirements")
    node = plan.get("node_configuration")
    topology = plan.get("topology")
    performance = plan.get("expected_performance")
    candidates = plan.get("gpu_candidates")
    if not isinstance(gpu, dict):
        errors.append(f"{path}.gpu_requirements must be an object")
        return
    if not isinstance(node, dict):
        errors.append(f"{path}.node_configuration must be an object")
        return
    if not isinstance(topology, dict):
        errors.append(f"{path}.topology must be an object")
        return
    if not isinstance(candidates, list) or len(candidates) > 3:
        errors.append(f"{path}.gpu_candidates must be an array with at most 3 items")
        candidates = []

    gpus_per_replica = gpu.get("gpus_per_replica")
    replicas = gpu.get("replicas")
    total_gpus = gpu.get("total_gpus")
    if not all(isinstance(x, int) and x > 0 for x in (gpus_per_replica, replicas)):
        errors.append(f"{path} GPU counts must be positive integers")
    elif total_gpus != gpus_per_replica * replicas:
        errors.append(f"{path}.total_gpus arithmetic mismatch")
    if expected_tier == "economic" and isinstance(replicas, int) and replicas < 1:
        errors.append("economic requires at least one replica")
    if (
        expected_tier == "peak_production"
        and isinstance(replicas, int)
        and replicas < 2
    ):
        errors.append("peak_production requires at least two replicas")

    nodes_per_replica = node.get("nodes_per_replica")
    total_nodes = node.get("total_nodes")
    if (
        isinstance(nodes_per_replica, int)
        and isinstance(replicas, int)
        and total_nodes != nodes_per_replica * replicas
    ):
        errors.append(f"{path}.total_nodes arithmetic mismatch")
    if (
        isinstance(node.get("vcpu_per_node"), int)
        and isinstance(total_nodes, int)
        and node.get("total_vcpu") != node["vcpu_per_node"] * total_nodes
    ):
        errors.append(f"{path}.total_vcpu arithmetic mismatch")
    if (
        isinstance(node.get("memory_gb_per_node"), int)
        and isinstance(total_nodes, int)
        and node.get("total_memory_gb")
        != node["memory_gb_per_node"] * total_nodes
    ):
        errors.append(f"{path}.total_memory_gb arithmetic mismatch")
    for item in candidates:
        if item.get("quantity_per_replica") != gpus_per_replica:
            errors.append(f"{path} candidate quantity does not match topology")
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"{path} references missing evidence {evidence_id}")

    if topology.get("replicas") != replicas:
        errors.append(f"{path}.topology.replicas mismatch")
    if topology.get("data_parallel") != replicas:
        errors.append(f"{path}.topology.data_parallel mismatch")

    if not isinstance(performance, dict):
        errors.append(f"{path}.expected_performance must be an object")
    else:
        status = performance.get("status")
        if status not in ("verified", "estimated", "benchmark_required"):
            errors.append(f"{path}.expected_performance.status is invalid")
        if status == "benchmark_required":
            numeric_fields = (
                "ttft_ms_p95",
                "itl_ms_p95",
                "output_tps_per_request",
                "prefill_tps_total",
                "decode_tps_total",
            )
            if any(performance.get(field) is not None for field in numeric_fields):
                errors.append(
                    f"{path} benchmark_required performance values must be null"
                )
        for evidence_id in performance.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"{path} references missing evidence {evidence_id}")


def validate(payload: Any) -> list[str]:
    errors: list[str] = []
    require_keys(errors, payload, TOP_LEVEL_KEYS, "$", exact=True)
    if not isinstance(payload, dict):
        return errors
    if payload.get("schema_version") != "1.5":
        errors.append("schema_version must be 1.5")
    require_keys(
        errors, payload.get("request_summary"), REQUEST_KEYS, "request_summary", exact=True
    )
    request = payload.get("request_summary")
    if isinstance(request, dict):
        if request.get("quantization_policy") not in (
            "preserve",
            "validated_only",
            "cost_first",
        ):
            errors.append("request_summary.quantization_policy is invalid")
        if request.get("response_mode") not in ("streaming", "non_streaming"):
            errors.append("request_summary.response_mode is invalid")
        tps = request.get("target_output_tps_per_request")
        itl = request.get("derived_target_itl_ms")
        if isinstance(tps, (int, float)) and isinstance(itl, (int, float)):
            if abs(itl - 1000 / tps) > 0.01:
                errors.append("derived_target_itl_ms does not match Token/s")

    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
        evidence = []
    for index, item in enumerate(evidence):
        path = f"evidence[{index}]"
        require_keys(errors, item, EVIDENCE_KEYS, path, exact=True)
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        source_type = item.get("source_type")
        if source_type not in EVIDENCE_SOURCE_TYPES:
            errors.append(f"{path}.source_type is invalid")
        elif category in SOURCE_TYPES_BY_CATEGORY:
            if source_type not in SOURCE_TYPES_BY_CATEGORY[category]:
                errors.append(
                    f"{path}.source_type {source_type} is not allowed for {category}"
                )
        else:
            errors.append(f"{path}.category is invalid")
        if not isinstance(item.get("publisher"), str) or not item["publisher"].strip():
            errors.append(f"{path}.publisher must be a non-empty string")
        if not isinstance(item.get("url"), str) or not item["url"].startswith(
            ("https://", "http://")
        ):
            errors.append(f"{path}.url must be a direct HTTP(S) URL")
    evidence_ids = {
        item.get("id")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(evidence_ids) != len(evidence):
        errors.append("evidence IDs must be present and unique")

    plans = payload.get("plans")
    if not isinstance(plans, list) or len(plans) != 2:
        errors.append("plans must contain exactly two objects")
    else:
        validate_plan(plans[0], "economic", evidence_ids, errors)
        validate_plan(plans[1], "peak_production", evidence_ids, errors)

    for path, key in walk_keys(payload):
        if key.lower() in FORBIDDEN_KEYS:
            errors.append(f"forbidden field {path}.{key}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "json_file",
        nargs="?",
        type=Path,
        help="Result JSON file; omit to read stdin",
    )
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw = (
            args.json_file.read_text(encoding="utf-8")
            if args.json_file
            else sys.stdin.read()
        )
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}))
        raise SystemExit(1)
    errors = validate(payload)
    print(
        json.dumps(
            {"valid": not errors, "errors": errors},
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
