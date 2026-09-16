#!/usr/bin/env python3
"""Calculate platform-neutral memory-only LLM serving requirements.

This module intentionally does not predict throughput or latency.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite number zero or greater")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def usable_ratio(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 1:
        raise argparse.ArgumentTypeError("must be in the interval (0, 1]")
    return number


def rounded(value: float) -> float:
    return round(value, 3)


def kv_bytes_per_token(
    *,
    attention_kind: str,
    layers: int | None,
    kv_heads: int | None,
    head_dim: int | None,
    kv_bits: float,
    measured_kv_bytes_per_token: float | None,
) -> tuple[float, str]:
    """Return KV bytes/token and the basis used."""
    if attention_kind != "generic":
        if measured_kv_bytes_per_token is None:
            raise ValueError(
                "special attention requires --kv-bytes-per-token from official "
                "documentation or runtime measurement"
            )
        return measured_kv_bytes_per_token, "official_or_measured_override"

    if measured_kv_bytes_per_token is not None:
        return measured_kv_bytes_per_token, "official_or_measured_override"
    if layers is None or kv_heads is None or head_dim is None:
        raise ValueError(
            "generic attention requires --layers, --kv-heads and --head-dim "
            "unless --kv-bytes-per-token is supplied"
        )
    value = 2 * layers * kv_heads * head_dim * kv_bits / 8
    return value, "generic_transformer_formula"


def calculate_tier_memory(
    *,
    parameters_b: float,
    weight_bits: float,
    kv_bits: float,
    live_tokens: int,
    workspace_ratio: float,
    gpu_vram_gb: float | None,
    usable_vram_ratio: float,
    attention_kind: str,
    layers: int | None,
    kv_heads: int | None,
    head_dim: int | None,
    measured_kv_bytes_per_token: float | None,
) -> dict[str, Any]:
    kv_bpt, kv_basis = kv_bytes_per_token(
        attention_kind=attention_kind,
        layers=layers,
        kv_heads=kv_heads,
        head_dim=head_dim,
        kv_bits=kv_bits,
        measured_kv_bytes_per_token=measured_kv_bytes_per_token,
    )
    weight_gb = parameters_b * weight_bits / 8
    kv_cache_gb = kv_bpt * live_tokens / 1e9
    workspace_gb = (weight_gb + kv_cache_gb) * workspace_ratio
    required_gb = weight_gb + kv_cache_gb + workspace_gb
    usable_gb = (
        gpu_vram_gb * usable_vram_ratio if gpu_vram_gb is not None else None
    )
    return {
        "weight_gb": rounded(weight_gb),
        "kv_bytes_per_token": rounded(kv_bpt),
        "kv_calculation_basis": kv_basis,
        "kv_cache_gb": rounded(kv_cache_gb),
        "workspace_ratio": workspace_ratio,
        "workspace_reserve_gb": rounded(workspace_gb),
        "required_vram_per_replica_gb": rounded(required_gb),
        "usable_vram_ratio": usable_vram_ratio,
        "usable_vram_per_gpu_gb": rounded(usable_gb) if usable_gb is not None else None,
        "gpus_per_replica_by_memory": math.ceil(required_gb / usable_gb) if usable_gb is not None else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate economic and peak-production memory requirements. "
            "Use total resident parameters for MoE models."
        )
    )
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
    parser.add_argument(
        "--kv-bytes-per-token",
        type=positive_float,
        help="Official or measured override; required for special attention",
    )
    parser.add_argument("--economic-weight-bits", type=positive_float, required=True)
    parser.add_argument(
        "--peak-production-weight-bits", type=positive_float, required=True
    )
    parser.add_argument("--economic-kv-bits", type=positive_float, default=16)
    parser.add_argument("--peak-production-kv-bits", type=positive_float, default=16)
    parser.add_argument("--typical-live-tokens", type=positive_int, required=True)
    parser.add_argument("--peak-live-tokens", type=positive_int, required=True)
    parser.add_argument("--workspace-ratio", type=nonnegative_float, default=0.20)
    parser.add_argument("--gpu-vram-gb", type=positive_float, required=True)
    parser.add_argument(
        "--economic-usable-ratio", type=usable_ratio, default=0.90
    )
    parser.add_argument(
        "--peak-production-usable-ratio", type=usable_ratio, default=0.85
    )
    parser.add_argument("--pretty", action="store_true")
    return parser


def calculate_namespace(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
) -> dict[str, Any]:
    parser = parser or build_parser()
    if args.active_parameters_b and args.active_parameters_b > args.parameters_b:
        parser.error("--active-parameters-b cannot exceed --parameters-b")
    if args.architecture == "dense" and args.active_parameters_b:
        parser.error("--active-parameters-b is only valid for MoE models")

    common = {
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
        economic = calculate_tier_memory(
            **common,
            weight_bits=args.economic_weight_bits,
            kv_bits=args.economic_kv_bits,
            live_tokens=args.typical_live_tokens,
            usable_vram_ratio=args.economic_usable_ratio,
        )
        peak = calculate_tier_memory(
            **common,
            weight_bits=args.peak_production_weight_bits,
            kv_bits=args.peak_production_kv_bits,
            live_tokens=args.peak_live_tokens,
            usable_vram_ratio=args.peak_production_usable_ratio,
        )
    except ValueError as exc:
        parser.error(str(exc))

    warnings = [
        "Memory capacity only; throughput and latency require comparable benchmarks.",
        "Align GPU count to parallel degrees supported by the model and engine.",
    ]
    if args.architecture == "moe":
        warnings.append(
            "MoE weight memory uses total resident parameters, not active parameters."
        )

    return {
        "units": "decimal_GB",
        "architecture": args.architecture,
        "attention_kind": args.attention_kind,
        "parameters": {
            "resident_total_b": args.parameters_b,
            "active_b": args.active_parameters_b,
            "weight_memory_basis": "resident_total_b",
        },
        "tiers": {
            "economic": economic,
            "peak_production": peak,
        },
        "performance_prediction": None,
        "warnings": warnings,
    }


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