#!/usr/bin/env python3
"""Validate and query the platform-neutral GPU hardware catalog."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import math
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


DEFAULT_CATALOG = Path(__file__).resolve().parent / "catalogs" / "gpu-catalog.json"
VENDOR_DOMAINS = {
    "NVIDIA": ("nvidia.com",),
    "AMD": ("amd.com",),
    "Intel": ("intel.com",),
    "MetaX": ("metax-tech.com",),
}
REQUIRED_DEVICE_FIELDS = {
    "id",
    "vendor",
    "model",
    "form_factor",
    "architecture",
    "memory_gb",
    "memory_type",
    "memory_bandwidth_gb_s",
    "precision_features",
    "dense_compute",
    "sparse_compute",
    "host_interface",
    "scale_up_interconnect",
    "tdp_w",
    "partitioning",
    "spec_status",
    "source",
    "notes",
}


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def max_results(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 5:
        raise argparse.ArgumentTypeError("must be between 1 and 5")
    return number


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}: {exc.msg}") from exc


def parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if not isinstance(catalog.get("devices"), list) or not catalog["devices"]:
        errors.append("devices must be a non-empty array")
        return errors
    policy = catalog.get("review_policy")
    if not isinstance(policy, dict) or not isinstance(
        policy.get("final_spec_recheck_days"), int
    ):
        errors.append("review_policy.final_spec_recheck_days must be an integer")

    ids: set[str] = set()
    for index, device in enumerate(catalog["devices"]):
        label = f"devices[{index}]"
        if not isinstance(device, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_DEVICE_FIELDS - set(device)
        if missing:
            errors.append(f"{label} missing fields: {sorted(missing)}")
            continue
        device_id = device["id"]
        if not isinstance(device_id, str) or not device_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif device_id in ids:
            errors.append(f"duplicate device id: {device_id}")
        ids.add(device_id)
        if device["spec_status"] not in ("final", "preliminary"):
            errors.append(f"{label}.spec_status must be final or preliminary")
        if not isinstance(device["memory_gb"], (int, float)) or device["memory_gb"] <= 0:
            errors.append(f"{label}.memory_gb must be positive")
        bandwidth = device["memory_bandwidth_gb_s"]
        if bandwidth is not None and (
            not isinstance(bandwidth, (int, float)) or bandwidth <= 0
        ):
            errors.append(f"{label}.memory_bandwidth_gb_s must be positive or null")
        if not isinstance(device["precision_features"], list):
            errors.append(f"{label}.precision_features must be an array")
        interconnect = device["scale_up_interconnect"]
        if interconnect is not None:
            if not isinstance(interconnect, dict):
                errors.append(f"{label}.scale_up_interconnect must be an object or null")
            else:
                required_interconnect = {
                    "name",
                    "bandwidth_gb_s",
                    "bandwidth_scope",
                    "max_devices",
                }
                missing_interconnect = required_interconnect - set(interconnect)
                if missing_interconnect:
                    errors.append(
                        f"{label}.scale_up_interconnect missing fields: "
                        f"{sorted(missing_interconnect)}"
                    )
                if not isinstance(interconnect.get("max_devices"), int) or (
                    interconnect.get("max_devices", 0) < 2
                ):
                    errors.append(
                        f"{label}.scale_up_interconnect.max_devices must be >= 2"
                    )
                interconnect_bandwidth = interconnect.get("bandwidth_gb_s")
                if interconnect_bandwidth is not None and (
                    not isinstance(interconnect_bandwidth, (int, float))
                    or interconnect_bandwidth <= 0
                ):
                    errors.append(
                        f"{label}.scale_up_interconnect.bandwidth_gb_s "
                        "must be positive or null"
                    )
        source = device["source"]
        if not isinstance(source, dict):
            errors.append(f"{label}.source must be an object")
            continue
        for key in ("title", "url", "published_at", "accessed_at"):
            if key not in source:
                errors.append(f"{label}.source missing {key}")
        url = source.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{label}.source.url must be a direct HTTPS URL")
        allowed = VENDOR_DOMAINS.get(device["vendor"])
        if allowed is None:
            errors.append(f"{label}.vendor has no trusted-domain rule")
        elif not any(
            parsed.netloc == domain or parsed.netloc.endswith("." + domain)
            for domain in allowed
        ):
            errors.append(
                f"{label}.source.url is not on an approved {device['vendor']} domain"
            )
        if source.get("accessed_at"):
            try:
                parse_date(source["accessed_at"], f"{label}.source.accessed_at")
            except ValueError as exc:
                errors.append(str(exc))
        if source.get("published_at") is not None:
            try:
                parse_date(source["published_at"], f"{label}.source.published_at")
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def filter_catalog(
    catalog: dict[str, Any],
    *,
    min_vram_gb: float,
    precision: str,
    vendors: set[str] | None,
    requires_scale_up: bool,
    final_only: bool,
    limit: int,
) -> dict[str, Any]:
    precision = precision.upper()
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    recheck_days = catalog["review_policy"]["final_spec_recheck_days"]
    today = date.today()

    for device in catalog["devices"]:
        if device["memory_gb"] < min_vram_gb:
            continue
        if precision not in {item.upper() for item in device["precision_features"]}:
            continue
        if vendors and device["vendor"].lower() not in vendors:
            continue
        if final_only and device["spec_status"] != "final":
            continue
        scale_up = device["scale_up_interconnect"]
        if requires_scale_up and (
            scale_up is None or (scale_up.get("max_devices") or 0) < 2
        ):
            continue

        accessed = parse_date(
            device["source"]["accessed_at"], f"{device['id']}.source.accessed_at"
        )
        age_days = (today - accessed).days
        requires_reverification = (
            device["spec_status"] == "preliminary" or age_days > recheck_days
        )
        if requires_reverification:
            warnings.append(f"{device['id']} requires official-source reverification")
        candidates.append(
            {
                "catalog_id": device["id"],
                "vendor": device["vendor"],
                "model": device["model"],
                "form_factor": device["form_factor"],
                "architecture": device["architecture"],
                "memory_gb": device["memory_gb"],
                "memory_type": device["memory_type"],
                "memory_bandwidth_gb_s": device["memory_bandwidth_gb_s"],
                "precision_features": device["precision_features"],
                "host_interface": device["host_interface"],
                "scale_up_interconnect": device["scale_up_interconnect"],
                "spec_status": device["spec_status"],
                "official_source_url": device["source"]["url"],
                "source_accessed_at": device["source"]["accessed_at"],
                "requires_reverification": requires_reverification,
                "notes": device["notes"],
            }
        )

    candidates.sort(
        key=lambda item: (
            item["memory_gb"] - min_vram_gb,
            -(item["memory_bandwidth_gb_s"] or 0),
            item["vendor"],
            item["model"],
        )
    )
    selected = candidates[:limit]
    return {
        "catalog_schema_version": catalog["schema_version"],
        "query": {
            "min_vram_gb": min_vram_gb,
            "precision": precision,
            "vendors": sorted(vendors) if vendors else None,
            "requires_scale_up": requires_scale_up,
            "final_only": final_only,
            "max_results": limit,
        },
        "match_count_before_limit": len(candidates),
        "candidates": selected,
        "warnings": sorted(set(warnings)),
        "selection_notice": (
            "Hardware prefilter only. Verify model, engine, quantization kernel, "
            "topology and performance evidence before recommending."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate catalog structure and sources")
    filter_parser = subparsers.add_parser(
        "filter", help="Return at most five hardware candidates"
    )
    filter_parser.add_argument("--min-vram-gb", type=positive_float, required=True)
    filter_parser.add_argument(
        "--precision",
        choices=("BF16", "FP16", "FP8", "FP4", "INT8", "INT4"),
        required=True,
    )
    filter_parser.add_argument(
        "--vendor",
        action="append",
        help="Vendor filter; may be supplied more than once",
    )
    filter_parser.add_argument("--requires-scale-up", action="store_true")
    filter_parser.add_argument("--final-only", action="store_true")
    filter_parser.add_argument("--max-results", type=max_results, default=5)
    return parser


def emit(payload: dict[str, Any], pretty: bool) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
    except ValueError as exc:
        parser.error(str(exc))
    errors = validate_catalog(catalog)

    if args.command == "validate":
        payload = {
            "valid": not errors,
            "device_count": len(catalog.get("devices", [])),
            "errors": errors,
        }
        emit(payload, args.pretty)
        raise SystemExit(0 if not errors else 1)

    if errors:
        emit({"valid": False, "errors": errors}, args.pretty)
        raise SystemExit(1)
    vendors = {value.lower() for value in args.vendor} if args.vendor else None
    known_vendors = {device["vendor"].lower() for device in catalog["devices"]}
    if vendors and not vendors <= known_vendors:
        parser.error(
            "unknown vendor(s): " + ", ".join(sorted(vendors - known_vendors))
        )
    payload = filter_catalog(
        catalog,
        min_vram_gb=args.min_vram_gb,
        precision=args.precision,
        vendors=vendors,
        requires_scale_up=args.requires_scale_up,
        final_only=args.final_only,
        limit=args.max_results,
    )
    emit(payload, args.pretty)


if __name__ == "__main__":
    main()
