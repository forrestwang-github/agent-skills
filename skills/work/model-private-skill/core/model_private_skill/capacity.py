#!/usr/bin/env python3
"""Build platform-neutral capacity calculations for two LLM serving tiers."""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from .memory import (
    calculate_tier_memory,
    nonnegative_float,
    positive_float,
    positive_int,
    rounded,
)


def hours_per_day(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 24:
        raise argparse.ArgumentTypeError("must be between 0 and 24")
    return number


def positive_int_list(value: str) -> list[int]:
    try:
        values = sorted({int(item.strip()) for item in value.split(",")})
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be comma-separated integers") from exc
    if not values or values[0] <= 0:
        raise argparse.ArgumentTypeError("all degrees must be positive")
    return values


def align_parallelism(required: int, supported: list[int]) -> int:
    for degree in supported:
        if degree >= required:
            return degree
    raise ValueError(
        f"required GPU count {required} exceeds largest supported parallel degree "
        f"{supported[-1]}"
    )


def derive_rps(
    *,
    supplied_rps: float | None,
    concurrency: int,
    ttft_ms: float | None,
    output_tokens: int,
    output_tps_per_request: float | None,
) -> tuple[float | None, str]:
    if supplied_rps is not None:
        return supplied_rps, "user_supplied"
    if ttft_ms is None or output_tps_per_request is None:
        return None, "unavailable"
    duration = ttft_ms / 1000 + output_tokens / output_tps_per_request
    return concurrency / duration, "derived_from_concurrency_and_duration"


def load_demand(
    *,
    concurrency: int,
    rps: float | None,
    input_tokens: int,
    output_tokens: int,
    output_tps_per_request: float | None,
) -> dict[str, float | int | None]:
    by_concurrency = (
        concurrency * output_tps_per_request
        if output_tps_per_request is not None
        else None
    )
    by_rps = rps * output_tokens if rps is not None else None
    decode_candidates = [x for x in (by_concurrency, by_rps) if x is not None]
    return {
        "active_concurrency": concurrency,
        "rps": rounded(rps) if rps is not None else None,
        "prefill_tps_required": rounded(rps * input_tokens)
        if rps is not None
        else None,
        "decode_tps_required": rounded(max(decode_candidates))
        if decode_candidates
        else None,
    }


def replicas_from_benchmark(
    demand: dict[str, Any],
    benchmark_prefill_tps: float | None,
    benchmark_decode_tps: float | None,
) -> int | None:
    ratios: list[float] = []
    if demand["prefill_tps_required"] is not None:
        if benchmark_prefill_tps is None:
            return None
        ratios.append(demand["prefill_tps_required"] / benchmark_prefill_tps)
    if demand["decode_tps_required"] is not None:
        if benchmark_decode_tps is None:
            return None
        ratios.append(demand["decode_tps_required"] / benchmark_decode_tps)
    if not ratios:
        return None
    return max(1, math.ceil(max(ratios)))


def choose_topology(gpus_per_replica: int, max_gpus_per_node: int) -> dict[str, int]:
    actual_gpus_per_node = min(gpus_per_replica, max_gpus_per_node)
    if gpus_per_replica <= max_gpus_per_node:
        return {
            "tensor_parallel": gpus_per_replica,
            "pipeline_parallel": 1,
            "gpus_per_node": actual_gpus_per_node,
            "nodes_per_replica": 1,
        }
    divisors = [
        value
        for value in range(1, max_gpus_per_node + 1)
        if gpus_per_replica % value == 0
    ]
    tp = max(divisors)
    pp = gpus_per_replica // tp
    return {
        "tensor_parallel": tp,
        "pipeline_parallel": pp,
        "gpus_per_node": tp,
        "nodes_per_replica": pp,
    }


def companion_resources(
    *,
    tier: str,
    gpus_per_node: int,
    total_nodes: int,
    artifact_gb: float,
    public_arrival_rps: float | None,
    public_response_rps: float | None,
    response_mode: str,
    active_concurrency: int,
    output_tps_per_request: float | None,
    input_tokens: int,
    output_tokens: int,
    bytes_per_token: float,
    protocol_overhead: float,
) -> dict[str, int | float | str | None]:
    if tier == "economic":
        vcpu = max(16, 8 * gpus_per_node)
        memory = max(128, math.ceil(artifact_gb * 1.25))
        system_disk = 100
        model_disk = math.ceil(artifact_gb * 1.2)
        shared_storage = math.ceil(artifact_gb * 1.2)
    else:
        vcpu = max(32, 16 * gpus_per_node)
        memory = max(256, math.ceil(artifact_gb * 1.50))
        system_disk = 200
        model_disk = math.ceil(artifact_gb * 2 * 1.2)
        shared_storage = math.ceil(artifact_gb * 2 * 1.2)

    public_access_ingress_peak_mbps: float | None = None
    public_access_egress_peak_mbps: float | None = None
    public_access_bandwidth_mbps: float | None = None
    if public_arrival_rps is not None:
        public_access_ingress_peak_mbps = rounded(
            public_arrival_rps
            * input_tokens
            * bytes_per_token
            * 8
            * protocol_overhead
            / 1e6
        )
    if response_mode == "streaming" and output_tps_per_request is not None:
        public_access_egress_peak_mbps = rounded(
            active_concurrency
            * output_tps_per_request
            * bytes_per_token
            * 8
            * protocol_overhead
            / 1e6
        )
    elif public_response_rps is not None:
        public_access_egress_peak_mbps = rounded(
            public_response_rps
            * output_tokens
            * bytes_per_token
            * 8
            * protocol_overhead
            / 1e6
        )
    if (
        public_access_ingress_peak_mbps is not None
        and public_access_egress_peak_mbps is not None
    ):
        public_access_bandwidth_mbps = max(
            public_access_ingress_peak_mbps, public_access_egress_peak_mbps
        )

    return {
        "vcpu_per_node": vcpu,
        "total_vcpu": vcpu * total_nodes,
        "memory_gb_per_node": memory,
        "total_memory_gb": memory * total_nodes,
        "system_disk_gb_per_node": system_disk,
        "total_system_disk_gb": system_disk * total_nodes,
        "model_disk_gb_per_node": model_disk,
        "total_model_disk_gb": model_disk * total_nodes,
        "shared_storage_gb": shared_storage,
        "public_access_ingress_peak_mbps": public_access_ingress_peak_mbps,
        "public_access_egress_peak_mbps": public_access_egress_peak_mbps,
        "public_access_bandwidth_mbps": public_access_bandwidth_mbps,
        "public_access_response_mode": response_mode,
    }


def build_parser(
    parser_factory: type[argparse.ArgumentParser] = argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    parser = parser_factory(
        description="Calculate typical/economic and peak/production LLM capacity."
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision")
    parser.add_argument("--parameters-b", type=positive_float, required=True)
    parser.add_argument("--architecture", choices=("dense", "moe"), default="dense")
    parser.add_argument("--active-parameters-b", type=positive_float)
    parser.add_argument(
        "--attention-kind",
        choices=("generic", "mla", "csa", "hca", "custom"),
        default="generic",
    )
    parser.add_argument("--layers", type=positive_int)
    parser.add_argument("--kv-heads", type=positive_int)
    parser.add_argument("--head-dim", type=positive_int)
    parser.add_argument("--kv-bytes-per-token", type=positive_float)
    parser.add_argument("--economic-weight-bits", type=positive_float, required=True)
    parser.add_argument(
        "--peak-production-weight-bits", type=positive_float, required=True
    )
    parser.add_argument("--economic-kv-bits", type=positive_float, default=16)
    parser.add_argument("--peak-production-kv-bits", type=positive_float, default=16)
    parser.add_argument("--typical-input-tokens", type=positive_int, required=True)
    parser.add_argument("--max-input-tokens", type=positive_int, required=True)
    parser.add_argument("--typical-output-tokens", type=positive_int, required=True)
    parser.add_argument("--max-output-tokens", type=positive_int, required=True)
    parser.add_argument("--typical-concurrency", type=positive_int, required=True)
    parser.add_argument("--peak-concurrency", type=positive_int, required=True)
    parser.add_argument("--peak-hours-per-day", type=hours_per_day, required=True)
    parser.add_argument("--max-length-concurrency", type=positive_int)
    parser.add_argument("--typical-rps", type=positive_float)
    parser.add_argument("--peak-rps", type=positive_float)
    parser.add_argument("--target-ttft-ms-p95", type=positive_float)
    parser.add_argument("--target-output-tps-per-request", type=positive_float)
    parser.add_argument(
        "--quantization-policy",
        choices=("preserve", "validated_only", "cost_first"),
        required=True,
    )
    parser.add_argument("--model-artifact-gb", type=positive_float, required=True)
    parser.add_argument("--gpu-vram-gb", type=positive_float)
    parser.add_argument("--max-gpus-per-node", type=positive_int, default=8)
    parser.add_argument(
        "--supported-parallel-degrees",
        type=positive_int_list,
        default=[1, 2, 4, 8, 16, 32, 64],
    )
    parser.add_argument("--workspace-ratio", type=nonnegative_float, default=0.20)
    parser.add_argument("--bytes-per-token", type=positive_float, default=4)
    parser.add_argument("--protocol-overhead", type=positive_float, default=1.3)
    parser.add_argument(
        "--response-mode",
        choices=("streaming", "non_streaming"),
        default="streaming",
    )
    parser.add_argument("--typical-response-rps", type=positive_float)
    parser.add_argument("--peak-response-rps", type=positive_float)
    for tier in ("economic", "peak-production"):
        parser.add_argument(
            f"--{tier}-benchmark-prefill-tps", type=positive_float
        )
        parser.add_argument(
            f"--{tier}-benchmark-decode-tps", type=positive_float
        )
        parser.add_argument(
            f"--{tier}-benchmark-gpus-per-replica", type=positive_int
        )
        parser.add_argument(
            f"--{tier}-benchmark-match", choices=("exact", "similar")
        )
    parser.add_argument("--failure-retains-full-peak", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.active_parameters_b and args.active_parameters_b > args.parameters_b:
        parser.error("--active-parameters-b cannot exceed --parameters-b")
    if args.architecture == "dense" and args.active_parameters_b:
        parser.error("--active-parameters-b is only valid for MoE models")
    if args.max_input_tokens < args.typical_input_tokens:
        parser.error("--max-input-tokens cannot be smaller than typical input")
    if args.max_output_tokens < args.typical_output_tokens:
        parser.error("--max-output-tokens cannot be smaller than typical output")
    if args.peak_concurrency < args.typical_concurrency:
        parser.error("--peak-concurrency cannot be smaller than typical concurrency")
    for tier_key in ("economic", "peak_production"):
        values = (
            getattr(args, f"{tier_key}_benchmark_prefill_tps"),
            getattr(args, f"{tier_key}_benchmark_decode_tps"),
            getattr(args, f"{tier_key}_benchmark_gpus_per_replica"),
            getattr(args, f"{tier_key}_benchmark_match"),
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            cli_tier = tier_key.replace("_", "-")
            parser.error(
                f"all four --{cli_tier}-benchmark-* arguments are required together"
            )


def calculate_namespace(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
) -> dict[str, Any]:
    parser = parser or build_parser()
    validate_args(parser, args)

    typical_rps, typical_rps_basis = derive_rps(
        supplied_rps=args.typical_rps,
        concurrency=args.typical_concurrency,
        ttft_ms=args.target_ttft_ms_p95,
        output_tokens=args.typical_output_tokens,
        output_tps_per_request=args.target_output_tps_per_request,
    )
    peak_rps, peak_rps_basis = derive_rps(
        supplied_rps=args.peak_rps,
        concurrency=args.peak_concurrency,
        ttft_ms=args.target_ttft_ms_p95,
        output_tokens=args.max_output_tokens,
        output_tps_per_request=args.target_output_tps_per_request,
    )
    typical_demand = load_demand(
        concurrency=args.typical_concurrency,
        rps=typical_rps,
        input_tokens=args.typical_input_tokens,
        output_tokens=args.typical_output_tokens,
        output_tps_per_request=args.target_output_tps_per_request,
    )
    peak_demand = load_demand(
        concurrency=args.peak_concurrency,
        rps=peak_rps,
        input_tokens=args.typical_input_tokens,
        output_tokens=args.typical_output_tokens,
        output_tps_per_request=args.target_output_tps_per_request,
    )

    typical_live_tokens = args.typical_concurrency * (
        args.typical_input_tokens + args.typical_output_tokens
    )
    peak_live_tokens = args.peak_concurrency * (
        args.typical_input_tokens + args.typical_output_tokens
    )
    memory_common = {
        "parameters_b": args.parameters_b,
        "workspace_ratio": args.workspace_ratio,
        "gpu_vram_gb": args.gpu_vram_gb,
        "attention_kind": args.attention_kind,
        "layers": args.layers,
        "kv_heads": args.kv_heads,
        "head_dim": args.head_dim,
        "measured_kv_bytes_per_token": args.kv_bytes_per_token,
    }
    try:
        economic_memory = calculate_tier_memory(
            **memory_common,
            weight_bits=args.economic_weight_bits,
            kv_bits=args.economic_kv_bits,
            live_tokens=typical_live_tokens,
            usable_vram_ratio=0.90,
        )
        peak_memory = calculate_tier_memory(
            **memory_common,
            weight_bits=args.peak_production_weight_bits,
            kv_bits=args.peak_production_kv_bits,
            live_tokens=peak_live_tokens,
            usable_vram_ratio=0.85,
        )
        max_low_memory = calculate_tier_memory(
            **memory_common,
            weight_bits=args.peak_production_weight_bits,
            kv_bits=args.peak_production_kv_bits,
            live_tokens=args.max_input_tokens + args.max_output_tokens,
            usable_vram_ratio=0.85,
        )
        max_high_concurrency = (
            args.max_length_concurrency
            if args.max_length_concurrency is not None
            else args.peak_concurrency
        )
        max_high_memory = calculate_tier_memory(
            **memory_common,
            weight_bits=args.peak_production_weight_bits,
            kv_bits=args.peak_production_kv_bits,
            live_tokens=max_high_concurrency
            * (args.max_input_tokens + args.max_output_tokens),
            usable_vram_ratio=0.85,
        )
    except ValueError as exc:
        parser.error(str(exc))

    tiers: dict[str, Any] = {}
    warnings: list[str] = []
    if args.architecture == "moe":
        warnings.append(
            "MoE weight memory used total resident parameters; active parameters "
            "were not used for weight capacity."
        )
    if typical_rps_basis != "user_supplied" or peak_rps_basis != "user_supplied":
        warnings.append(
            "Missing RPS was derived from concurrency and estimated request duration."
        )
        warnings.append(
            "Public ingress bandwidth is unset for tiers without user-supplied arrival RPS."
        )
    if args.response_mode == "non_streaming" and (
        args.typical_response_rps is None or args.peak_response_rps is None
    ):
        warnings.append(
            "Non-streaming public egress bandwidth is unset without response-completion RPS."
        )
    if args.target_output_tps_per_request is None:
        warnings.append(
            "Per-request Token/s is missing; decode performance demand is incomplete."
        )
    if args.max_length_concurrency is None:
        warnings.append(
            "Maximum-length concurrency is unknown; peak safety is reported as a range."
        )

    tier_inputs = (
        (
            "economic",
            economic_memory,
            typical_demand,
            args.economic_benchmark_prefill_tps,
            args.economic_benchmark_decode_tps,
            args.economic_benchmark_gpus_per_replica,
            args.economic_benchmark_match,
            1,
            typical_rps,
            args.typical_response_rps,
            args.typical_concurrency,
            typical_rps_basis,
        ),
        (
            "peak_production",
            peak_memory,
            peak_demand,
            args.peak_production_benchmark_prefill_tps,
            args.peak_production_benchmark_decode_tps,
            args.peak_production_benchmark_gpus_per_replica,
            args.peak_production_benchmark_match,
            2,
            peak_rps,
            args.peak_response_rps,
            args.peak_concurrency,
            peak_rps_basis,
        ),
    )
    for (
        tier,
        memory,
        demand,
        benchmark_prefill,
        benchmark_decode,
        benchmark_gpus,
        benchmark_match,
        minimum_replicas,
        planning_rps,
        response_rps,
        active_concurrency,
        rps_basis,
    ) in tier_inputs:
        replicas_by_performance = replicas_from_benchmark(
            demand, benchmark_prefill, benchmark_decode
        )
        if args.gpu_vram_gb is None:
            replicas = max(minimum_replicas, replicas_by_performance or minimum_replicas)
            tiers[tier] = {
                "load_demand": demand,
                "memory": memory,
                "gpu_capacity": {
                    "gpus_per_replica_by_memory": None,
                    "gpus_per_replica_by_performance": benchmark_gpus,
                    "gpus_per_replica": None,
                    "replicas_by_performance": replicas_by_performance,
                    "replicas": replicas,
                    "total_gpus": None,
                    "parallelism_alignment": args.supported_parallel_degrees,
                },
                "topology": None,
                "node_configuration": None,
                "performance_status": (
                    "verified" if benchmark_match == "exact"
                    else "estimated" if benchmark_match == "similar"
                    else "benchmark_required"
                ),
            }
            continue
        per_replica_required = max(
            memory["gpus_per_replica_by_memory"], benchmark_gpus or 0
        )
        try:
            gpus_per_replica = align_parallelism(
                per_replica_required, args.supported_parallel_degrees
            )
        except ValueError as exc:
            parser.error(str(exc))
        replicas = max(minimum_replicas, replicas_by_performance or minimum_replicas)
        if tier == "peak_production" and args.failure_retains_full_peak:
            replicas = (
                max(2, 2 * replicas_by_performance)
                if replicas_by_performance is not None
                else 2
            )
        topology = choose_topology(gpus_per_replica, args.max_gpus_per_node)
        total_nodes = topology["nodes_per_replica"] * replicas
        resources = companion_resources(
            tier=tier,
            gpus_per_node=topology["gpus_per_node"],
            total_nodes=total_nodes,
            artifact_gb=args.model_artifact_gb,
            public_arrival_rps=(
                planning_rps if rps_basis == "user_supplied" else None
            ),
            public_response_rps=response_rps,
            response_mode=args.response_mode,
            active_concurrency=active_concurrency,
            output_tps_per_request=args.target_output_tps_per_request,
            input_tokens=(
                args.typical_input_tokens if tier == "economic" else args.max_input_tokens
            ),
            output_tokens=(
                args.typical_output_tokens if tier == "economic" else args.max_output_tokens
            ),
            bytes_per_token=args.bytes_per_token,
            protocol_overhead=args.protocol_overhead,
        )
        performance_status = (
            "verified"
            if benchmark_match == "exact"
            else "estimated"
            if benchmark_match == "similar"
            else "benchmark_required"
        )
        tiers[tier] = {
            "load_demand": demand,
            "memory": memory,
            "gpu_capacity": {
                "gpus_per_replica_by_memory": memory[
                    "gpus_per_replica_by_memory"
                ],
                "gpus_per_replica_by_performance": benchmark_gpus,
                "gpus_per_replica": gpus_per_replica,
                "replicas_by_performance": replicas_by_performance,
                "replicas": replicas,
                "total_gpus": gpus_per_replica * replicas,
                "parallelism_alignment": args.supported_parallel_degrees,
            },
            "topology": {
                **topology,
                "data_parallel": replicas,
                "replicas": replicas,
                "load_balancing": "none"
                if replicas == 1
                else "active-active",
            },
            "node_configuration": {
                "total_nodes": total_nodes,
                **resources,
            },
            "performance_status": performance_status,
        }

    max_low_cards = max_low_memory["gpus_per_replica_by_memory"]
    max_high_cards = max_high_memory["gpus_per_replica_by_memory"]
    result = {
        "calculation_version": "1.3",
        "request_summary": {
            "model_id": args.model_id,
            "model_revision": args.model_revision,
            "typical_input_tokens": args.typical_input_tokens,
            "max_input_tokens": args.max_input_tokens,
            "typical_output_tokens": args.typical_output_tokens,
            "max_output_tokens": args.max_output_tokens,
            "typical_active_concurrency": args.typical_concurrency,
            "peak_active_concurrency": args.peak_concurrency,
            "peak_duration_hours_per_day": args.peak_hours_per_day,
            "typical_rps": rounded(typical_rps)
            if typical_rps is not None
            else None,
            "typical_rps_basis": typical_rps_basis,
            "peak_rps": rounded(peak_rps) if peak_rps is not None else None,
            "peak_rps_basis": peak_rps_basis,
            "response_mode": args.response_mode,
            "typical_response_rps": args.typical_response_rps,
            "peak_response_rps": args.peak_response_rps,
            "target_ttft_ms_p95": args.target_ttft_ms_p95,
            "target_output_tps_per_request": args.target_output_tps_per_request,
            "derived_target_itl_ms": rounded(
                1000 / args.target_output_tps_per_request
            )
            if args.target_output_tps_per_request is not None
            else None,
            "quantization_policy": args.quantization_policy,
        },
        "model_basis": {
            "architecture": args.architecture,
            "attention_kind": args.attention_kind,
            "resident_total_parameters_b": args.parameters_b,
            "active_parameters_b": args.active_parameters_b,
            "model_artifact_gb": args.model_artifact_gb,
        },
        "load_normalization": {
            "typical": typical_demand,
            "peak": peak_demand,
            "daily_equivalent_concurrency": rounded(
                (
                    args.typical_concurrency * (24 - args.peak_hours_per_day)
                    + args.peak_concurrency * args.peak_hours_per_day
                )
                / 24
            ),
        },
        "max_length_safety": {
            "max_length_concurrency_supplied": args.max_length_concurrency,
            "assumed_concurrency_range": [
                1,
                max_high_concurrency,
            ],
            "gpus_per_replica_by_memory_range": [
                max_low_cards,
                max_high_cards,
            ],
            "crosses_gpu_count_boundary": max_low_cards != max_high_cards,
        },
        "tiers": tiers,
        "performance_prediction": None
        if all(
            tier["performance_status"] == "benchmark_required"
            for tier in tiers.values()
        )
        else "benchmark_capacity_only",
        "warnings": warnings,
    }
    return result


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = calculate_namespace(args, parser)
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )


if __name__ == "__main__":
    main()