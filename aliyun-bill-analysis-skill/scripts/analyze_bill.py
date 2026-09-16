#!/usr/bin/env python3
"""Unified CLI for file-based and API-based bill analysis."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bill_analyzer import analyze_records
from bill_models import ValidationIssue, ValidationResult
from bill_report import generate_report
from bill_sources import BSSBillSource, FileBillSource
from bill_validator import validate_import


def parse_month_range(from_month: str, to_month: str) -> List[str]:
    start = datetime.strptime(from_month, "%Y-%m")
    end = datetime.strptime(to_month, "%Y-%m")
    if start > end:
        raise ValueError("起始月份不能晚于结束月份")
    months: List[str] = []
    current = start
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    return value[:80] or "客户"


def _build_run_dir(base: Path, customer_name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = base / f"{stamp}_{_safe_name(customer_name)}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run(args: argparse.Namespace) -> int:
    output_base = Path(args.output_dir or SKILL_DIR / "output").resolve()
    run_dir = _build_run_dir(output_base, args.customer)
    type_map_path = SKILL_DIR / "references" / "billing-type-map.json"

    try:
        expected_months = _expected_months(args)
        if args.command == "file":
            _log(f"读取账单文件: {Path(args.input).resolve()}")
            imported = FileBillSource(type_map_path).load(Path(args.input))
        else:
            access_key_id = args.ak or os.environ.get(
                "ALIBABA_CLOUD_ACCESS_KEY_ID", ""
            )
            access_key_secret = args.sk or os.environ.get(
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""
            )
            if not access_key_id or not access_key_secret:
                raise ValueError("API入口缺少AK/SK")
            masked = access_key_id[-4:] if len(access_key_id) >= 4 else "****"
            _log(f"使用AK末四位 {masked} 拉取 {len(expected_months)} 个月账单")
            imported = BSSBillSource(
                access_key_id, access_key_secret, type_map_path
            ).fetch(
                expected_months,
                product_code=args.product,
                bill_owner_id=args.owner,
            )

        manifest_path = run_dir / "manifest.json"
        _write_json(manifest_path, imported.manifest)

        validation = validate_import(
            imported,
            expected_months=expected_months or None,
            allow_multiple_accounts=args.allow_multiple_accounts,
        )
        validation_path = run_dir / "validation.json"
        _write_json(validation_path, validation.to_dict())
        if not validation.passed:
            payload = {
                "status": "failed",
                "code": "VALIDATION_FAILED",
                "run_dir": str(run_dir),
                "validation_path": str(validation_path),
            }
            print(json.dumps(payload, ensure_ascii=False))
            return 2

        analysis = analyze_records(
            validation,
            customer_name=args.customer,
            group_by_region=not args.no_region,
            top_n=args.top_n,
        )
        analysis_path = run_dir / "analysis-result.json"
        _write_json(analysis_path, analysis.to_dict())

        months = analysis.data["months"]
        report_name = (
            f"阿里云账单分析_{_safe_name(args.customer)}_"
            f"{months[0]}_{months[-1]}.xlsx"
        )
        report_path = run_dir / report_name
        generate_report(
            analysis.to_dict(),
            imported.manifest,
            validation,
            report_path,
        )
        payload = {
            "status": "ok",
            "run_dir": str(run_dir),
            "report_path": str(report_path),
            "validation_status": "passed",
            "record_count": len(validation.records),
            "months": months,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        failure = ValidationResult(
            errors=[
                ValidationIssue(
                    severity="error",
                    code="UNHANDLED_ERROR",
                    message=str(exc),
                )
            ]
        )
        validation_path = run_dir / "validation.json"
        if not validation_path.exists():
            _write_json(validation_path, failure.to_dict())
        payload = {
            "status": "failed",
            "code": "UNHANDLED_ERROR",
            "message": str(exc),
            "run_dir": str(run_dir),
            "validation_path": str(validation_path),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1


def _expected_months(args: argparse.Namespace) -> List[str]:
    from_month = getattr(args, "from_month", None)
    to_month = getattr(args, "to_month", None)
    if not from_month and not to_month:
        if args.command == "api":
            raise ValueError("API入口必须指定 --from 和 --to")
        return []
    if not from_month:
        from_month = to_month
    if not to_month:
        to_month = from_month
    return parse_month_range(from_month, to_month)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="阿里云历史账单确定性分析"
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--from", dest="from_month", help="起始月份 YYYY-MM")
    common.add_argument("--to", dest="to_month", help="结束月份 YYYY-MM")
    common.add_argument("--customer", default="", help="客户名称")
    common.add_argument("--output-dir", help="输出根目录")
    common.add_argument(
        "--allow-multiple-accounts",
        action="store_true",
        help="允许汇总多个资源购买账号",
    )
    common.add_argument(
        "--no-region",
        action="store_true",
        help="后付费计费项不按地域拆分",
    )
    common.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="趋势页展示费用最高的前N项",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    file_parser = subparsers.add_parser(
        "file", parents=[common], help="分析CSV/XLSX/ZIP或目录"
    )
    file_parser.add_argument("--input", required=True, help="文件或目录")

    api_parser = subparsers.add_parser(
        "api", parents=[common], help="使用AK/SK拉取账单"
    )
    api_parser.add_argument("--ak", help="AccessKey ID")
    api_parser.add_argument("--sk", help="AccessKey Secret")
    api_parser.add_argument("--product", help="产品Code过滤")
    api_parser.add_argument("--owner", help="账单归属账号ID")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.top_n < 1:
        parser.error("--top-n 必须大于0")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
