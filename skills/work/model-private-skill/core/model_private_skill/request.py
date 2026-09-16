"""Normalize and execute platform-neutral JSON capacity requests."""

from __future__ import annotations

import argparse
from typing import Any

from . import capacity
from .selection import select_gpu_configurations


class InputValidationError(ValueError):
    """Raised when a platform-neutral request is invalid."""


class RaisingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputValidationError(message)


ALLOWED_TOP_LEVEL = {
    "schema_version",
    "model",
    "workload",
    "slo",
    "precision",
    "hardware_profile",
    "engineering",
    "benchmarks",
}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "model",
    "workload",
    "slo",
    "precision",
}


def _object_at(request: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = request.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _positive(
    obj: dict[str, Any],
    key: str,
    path: str,
    errors: list[str],
    *,
    required: bool = True,
    integer: bool = False,
) -> None:
    value = obj.get(key)
    if value is None and not required:
        return
    expected = int if integer else (int, float)
    if not isinstance(value, expected) or isinstance(value, bool) or value <= 0:
        errors.append(f"{path}.{key} must be a positive {'integer' if integer else 'number'}")


def _check_allowed(
    obj: dict[str, Any], allowed: set[str], path: str, errors: list[str]
) -> None:
    extra = set(obj) - allowed
    if extra:
        errors.append(f"{path} has unsupported fields: {sorted(extra)}")


def _require_keys(
    obj: dict[str, Any], required: set[str], path: str, errors: list[str]
) -> None:
    missing = required - set(obj)
    if missing:
        errors.append(f"{path} missing fields: {sorted(missing)}")


def validate_request(request: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(request, dict):
        return ["request must be an object"]
    missing = REQUIRED_TOP_LEVEL - set(request)
    if missing:
        errors.append(f"request missing fields: {sorted(missing)}")
    _check_allowed(request, ALLOWED_TOP_LEVEL, "request", errors)
    if request.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")

    model = _object_at(request, "model", errors)
    workload = _object_at(request, "workload", errors)
    slo = _object_at(request, "slo", errors)
    precision = _object_at(request, "precision", errors)
    hardware = request.get("hardware_profile", {})
    if not isinstance(hardware, dict):
        errors.append("hardware_profile must be an object when provided")
        hardware = {}
    engineering = request.get("engineering", {})
    benchmarks = request.get("benchmarks", {})
    if not isinstance(engineering, dict):
        errors.append("engineering must be an object")
        engineering = {}
    if not isinstance(benchmarks, dict):
        errors.append("benchmarks must be an object")
        benchmarks = {}

    _check_allowed(
        model,
        {
            "id",
            "revision",
            "architecture",
            "parameters_b",
            "active_parameters_b",
            "artifact_gb",
            "attention",
        },
        "model",
        errors,
    )
    _require_keys(
        model,
        {
            "id",
            "revision",
            "architecture",
            "parameters_b",
            "active_parameters_b",
            "artifact_gb",
            "attention",
        },
        "model",
        errors,
    )
    if not isinstance(model.get("id"), str) or not model.get("id"):
        errors.append("model.id must be a non-empty string")
    if model.get("architecture") not in ("dense", "moe"):
        errors.append("model.architecture must be dense or moe")
    _positive(model, "parameters_b", "model", errors)
    _positive(model, "active_parameters_b", "model", errors, required=False)
    _positive(model, "artifact_gb", "model", errors)
    if (
        isinstance(model.get("active_parameters_b"), (int, float))
        and isinstance(model.get("parameters_b"), (int, float))
        and model["active_parameters_b"] > model["parameters_b"]
    ):
        errors.append("model.active_parameters_b cannot exceed parameters_b")
    if model.get("architecture") == "dense" and model.get("active_parameters_b") is not None:
        errors.append("model.active_parameters_b is only valid for MoE")

    attention = model.get("attention")
    if not isinstance(attention, dict):
        errors.append("model.attention must be an object")
        attention = {}
    _check_allowed(
        attention,
        {"kind", "layers", "kv_heads", "head_dim", "kv_bytes_per_token"},
        "model.attention",
        errors,
    )
    _require_keys(
        attention,
        {"kind", "layers", "kv_heads", "head_dim", "kv_bytes_per_token"},
        "model.attention",
        errors,
    )
    kind = attention.get("kind")
    if kind not in ("generic", "mla", "csa", "hca", "custom"):
        errors.append("model.attention.kind is invalid")
    for key in ("layers", "kv_heads", "head_dim"):
        _positive(
            attention,
            key,
            "model.attention",
            errors,
            required=False,
            integer=True,
        )
    _positive(
        attention,
        "kv_bytes_per_token",
        "model.attention",
        errors,
        required=False,
    )
    if kind == "generic" and attention.get("kv_bytes_per_token") is None:
        if any(attention.get(key) is None for key in ("layers", "kv_heads", "head_dim")):
            errors.append(
                "generic attention requires layers, kv_heads and head_dim, "
                "or kv_bytes_per_token"
            )
    if kind in ("mla", "csa", "hca", "custom") and attention.get(
        "kv_bytes_per_token"
    ) is None:
        errors.append("special attention requires official or measured kv_bytes_per_token")

    _check_allowed(
        workload,
        {
            "typical_input_tokens",
            "max_input_tokens",
            "typical_output_tokens",
            "max_output_tokens",
            "typical_active_concurrency",
            "peak_active_concurrency",
            "peak_duration_hours_per_day",
            "max_length_concurrency",
            "typical_rps",
            "peak_rps",
            "typical_response_rps",
            "peak_response_rps",
        },
        "workload",
        errors,
    )
    _require_keys(
        workload,
        {
            "typical_input_tokens",
            "max_input_tokens",
            "typical_output_tokens",
            "max_output_tokens",
            "typical_active_concurrency",
            "peak_active_concurrency",
            "peak_duration_hours_per_day",
            "max_length_concurrency",
            "typical_rps",
            "peak_rps",
        },
        "workload",
        errors,
    )
    for key in (
        "typical_input_tokens",
        "max_input_tokens",
        "typical_output_tokens",
        "max_output_tokens",
        "typical_active_concurrency",
        "peak_active_concurrency",
    ):
        _positive(workload, key, "workload", errors, integer=True)
    _positive(
        workload,
        "max_length_concurrency",
        "workload",
        errors,
        required=False,
        integer=True,
    )
    for key in (
        "typical_rps",
        "peak_rps",
        "typical_response_rps",
        "peak_response_rps",
    ):
        _positive(workload, key, "workload", errors, required=False)
    peak_hours = workload.get("peak_duration_hours_per_day")
    if (
        not isinstance(peak_hours, (int, float))
        or isinstance(peak_hours, bool)
        or not 0 <= peak_hours <= 24
    ):
        errors.append("workload.peak_duration_hours_per_day must be between 0 and 24")
    if all(
        isinstance(workload.get(key), int)
        for key in ("typical_input_tokens", "max_input_tokens")
    ) and workload["max_input_tokens"] < workload["typical_input_tokens"]:
        errors.append("max_input_tokens cannot be smaller than typical_input_tokens")
    if all(
        isinstance(workload.get(key), int)
        for key in ("typical_output_tokens", "max_output_tokens")
    ) and workload["max_output_tokens"] < workload["typical_output_tokens"]:
        errors.append("max_output_tokens cannot be smaller than typical_output_tokens")
    if all(
        isinstance(workload.get(key), int)
        for key in ("typical_active_concurrency", "peak_active_concurrency")
    ) and workload["peak_active_concurrency"] < workload["typical_active_concurrency"]:
        errors.append("peak_active_concurrency cannot be smaller than typical")

    _check_allowed(slo, {"ttft_ms_p95", "output_tps_per_request"}, "slo", errors)
    _require_keys(
        slo, {"ttft_ms_p95", "output_tps_per_request"}, "slo", errors
    )
    for key in ("ttft_ms_p95", "output_tps_per_request"):
        _positive(slo, key, "slo", errors, required=False)

    _check_allowed(
        precision,
        {
            "economic_weight_bits",
            "peak_production_weight_bits",
            "economic_kv_bits",
            "peak_production_kv_bits",
            "quantization_policy",
        },
        "precision",
        errors,
    )
    _require_keys(
        precision,
        {
            "economic_weight_bits",
            "peak_production_weight_bits",
            "economic_kv_bits",
            "peak_production_kv_bits",
            "quantization_policy",
        },
        "precision",
        errors,
    )
    for key in (
        "economic_weight_bits",
        "peak_production_weight_bits",
        "economic_kv_bits",
        "peak_production_kv_bits",
    ):
        _positive(precision, key, "precision", errors)
    if precision.get("quantization_policy") not in (
        "preserve",
        "validated_only",
        "cost_first",
    ):
        errors.append("precision.quantization_policy is invalid")

    if hardware:
        _check_allowed(
            hardware,
            {"gpu_vram_gb", "max_gpus_per_node", "supported_parallel_degrees"},
            "hardware_profile",
            errors,
        )
        _require_keys(
            hardware,
            {"gpu_vram_gb", "max_gpus_per_node", "supported_parallel_degrees"},
            "hardware_profile",
            errors,
        )
        _positive(hardware, "gpu_vram_gb", "hardware_profile", errors)
        _positive(
            hardware,
            "max_gpus_per_node",
            "hardware_profile",
            errors,
            integer=True,
        )
        degrees = hardware.get("supported_parallel_degrees")
        if not isinstance(degrees, list) or not degrees or any(
            not isinstance(value, int) or value <= 0 for value in degrees
        ):
            errors.append(
                "hardware_profile.supported_parallel_degrees must be positive integers"
            )


    _check_allowed(
        engineering,
        {
            "workspace_ratio",
            "bytes_per_token",
            "protocol_overhead",
            "response_mode",
            "failure_retains_full_peak",
        },
        "engineering",
        errors,
    )
    if "workspace_ratio" in engineering and (
        not isinstance(engineering["workspace_ratio"], (int, float))
        or engineering["workspace_ratio"] < 0
    ):
        errors.append("engineering.workspace_ratio must be zero or greater")
    for key in ("bytes_per_token", "protocol_overhead"):
        _positive(engineering, key, "engineering", errors, required=False)
    if engineering.get("response_mode") not in (None, "streaming", "non_streaming"):
        errors.append("engineering.response_mode must be streaming or non_streaming")
    if "failure_retains_full_peak" in engineering and not isinstance(
        engineering["failure_retains_full_peak"], bool
    ):
        errors.append("engineering.failure_retains_full_peak must be boolean")

    _check_allowed(
        benchmarks, {"economic", "peak_production"}, "benchmarks", errors
    )
    for tier in ("economic", "peak_production"):
        benchmark = benchmarks.get(tier)
        if benchmark is None:
            continue
        if not isinstance(benchmark, dict):
            errors.append(f"benchmarks.{tier} must be an object")
            continue
        allowed = {"prefill_tps", "decode_tps", "gpus_per_replica", "match"}
        _check_allowed(benchmark, allowed, f"benchmarks.{tier}", errors)
        if set(benchmark) != allowed:
            errors.append(f"benchmarks.{tier} must contain all benchmark fields")
            continue
        _positive(benchmark, "prefill_tps", f"benchmarks.{tier}", errors)
        _positive(benchmark, "decode_tps", f"benchmarks.{tier}", errors)
        _positive(
            benchmark,
            "gpus_per_replica",
            f"benchmarks.{tier}",
            errors,
            integer=True,
        )
        if benchmark.get("match") not in ("exact", "similar"):
            errors.append(f"benchmarks.{tier}.match must be exact or similar")
    return errors


def _add(argv: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    argv.extend((flag, str(value)))


def request_to_capacity_argv(request: dict[str, Any]) -> list[str]:
    errors = validate_request(request)
    if errors:
        raise InputValidationError("; ".join(errors))

    model = request["model"]
    attention = model["attention"]
    workload = request["workload"]
    slo = request["slo"]
    precision = request["precision"]
    hardware = request.get("hardware_profile") or {}
    engineering = request.get("engineering", {})
    benchmarks = request.get("benchmarks", {})
    argv: list[str] = []

    mappings = (
        ("--model-id", model["id"]),
        ("--model-revision", model.get("revision")),
        ("--parameters-b", model["parameters_b"]),
        ("--architecture", model["architecture"]),
        ("--active-parameters-b", model.get("active_parameters_b")),
        ("--attention-kind", attention["kind"]),
        ("--layers", attention.get("layers")),
        ("--kv-heads", attention.get("kv_heads")),
        ("--head-dim", attention.get("head_dim")),
        ("--kv-bytes-per-token", attention.get("kv_bytes_per_token")),
        ("--economic-weight-bits", precision["economic_weight_bits"]),
        (
            "--peak-production-weight-bits",
            precision["peak_production_weight_bits"],
        ),
        ("--economic-kv-bits", precision["economic_kv_bits"]),
        ("--peak-production-kv-bits", precision["peak_production_kv_bits"]),
        ("--typical-input-tokens", workload["typical_input_tokens"]),
        ("--max-input-tokens", workload["max_input_tokens"]),
        ("--typical-output-tokens", workload["typical_output_tokens"]),
        ("--max-output-tokens", workload["max_output_tokens"]),
        ("--typical-concurrency", workload["typical_active_concurrency"]),
        ("--peak-concurrency", workload["peak_active_concurrency"]),
        ("--peak-hours-per-day", workload["peak_duration_hours_per_day"]),
        ("--max-length-concurrency", workload.get("max_length_concurrency")),
        ("--typical-rps", workload.get("typical_rps")),
        ("--peak-rps", workload.get("peak_rps")),
        ("--typical-response-rps", workload.get("typical_response_rps")),
        ("--peak-response-rps", workload.get("peak_response_rps")),
        ("--target-ttft-ms-p95", slo.get("ttft_ms_p95")),
        ("--target-output-tps-per-request", slo.get("output_tps_per_request")),
        ("--quantization-policy", precision["quantization_policy"]),
        ("--model-artifact-gb", model["artifact_gb"]),
        ("--gpu-vram-gb", hardware.get("gpu_vram_gb")),
        ("--max-gpus-per-node", hardware.get("max_gpus_per_node")),
        (
            "--supported-parallel-degrees",
            ",".join(str(item) for item in hardware["supported_parallel_degrees"]) if hardware.get("supported_parallel_degrees") else None,
        ),
        ("--workspace-ratio", engineering.get("workspace_ratio")),
        ("--bytes-per-token", engineering.get("bytes_per_token")),
        ("--protocol-overhead", engineering.get("protocol_overhead")),
        ("--response-mode", engineering.get("response_mode")),
    )
    for flag, value in mappings:
        _add(argv, flag, value)
    if engineering.get("failure_retains_full_peak"):
        argv.append("--failure-retains-full-peak")
    for tier in ("economic", "peak_production"):
        benchmark = benchmarks.get(tier)
        if not benchmark:
            continue
        cli_tier = tier.replace("_", "-")
        _add(
            argv,
            f"--{cli_tier}-benchmark-prefill-tps",
            benchmark["prefill_tps"],
        )
        _add(
            argv,
            f"--{cli_tier}-benchmark-decode-tps",
            benchmark["decode_tps"],
        )
        _add(
            argv,
            f"--{cli_tier}-benchmark-gpus-per-replica",
            benchmark["gpus_per_replica"],
        )
        _add(argv, f"--{cli_tier}-benchmark-match", benchmark["match"])
    return argv


def calculate_request(request: dict[str, Any]) -> dict[str, Any]:
    parser = capacity.build_parser(parser_factory=RaisingArgumentParser)
    args = parser.parse_args(request_to_capacity_argv(request))
    result = capacity.calculate_namespace(args, parser)
    if not request.get("hardware_profile"):
        result["selection_mode"] = "auto_select"
        result["gpu_selection"] = select_gpu_configurations(result, request)
    else:
        result["selection_mode"] = "existing_hardware"
    return result