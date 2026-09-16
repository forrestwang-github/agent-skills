#!/usr/bin/env python3
"""File and BSS API sources that produce the same BillRecord model."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from bill_importer import BillFileImporter
from bill_models import ImportResult, ValidationIssue
from bill_schema import (
    BillingTypeMapper,
    build_header_mapping,
    map_row_to_record,
    parse_decimal,
)
from bss_client import BSSClient


class FileBillSource:
    def __init__(self, billing_type_map: Optional[Path] = None):
        self.importer = BillFileImporter(billing_type_map)

    def load(self, input_path: Path) -> ImportResult:
        return self.importer.load(input_path)


class BSSBillSource:
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        billing_type_map: Optional[Path] = None,
    ):
        if not access_key_id or not access_key_secret:
            raise ValueError("API入口需要完整的AK/SK")
        self.client = BSSClient(ak=access_key_id, sk=access_key_secret)
        self.billing_type_mapper = BillingTypeMapper(billing_type_map)

    def fetch(
        self,
        months: Sequence[str],
        *,
        product_code: Optional[str] = None,
        bill_owner_id: Optional[str] = None,
    ) -> ImportResult:
        result = ImportResult(
            manifest={
                "source": "api",
                "months_requested": list(months),
                "files": [],
                "raw_row_count": 0,
                "parsed_row_count": 0,
            }
        )
        for month in months:
            items, error = self.client.fetch_all_split_items(
                billing_cycle=month,
                product_code=product_code,
                bill_owner_id=bill_owner_id,
            )
            if error:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="API_MONTH_FAILED",
                        message=f"{month}账单拉取失败: {error}",
                    )
                )
                continue
            self._append_month(month, items, result)
            self._reconcile_overview(
                month,
                items,
                result,
                product_code=product_code,
                bill_owner_id=bill_owner_id,
            )
        result.manifest["parsed_row_count"] = len(result.records)
        return result

    def _append_month(
        self, month: str, items: List[Dict[str, Any]], result: ImportResult
    ) -> None:
        canonical = json.dumps(
            items,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        response_hash = hashlib.sha256(canonical).hexdigest()
        source_name = f"api:QuerySplitItemBill:{month}"
        source_manifest = {
            "name": source_name,
            "sha256": response_hash,
            "type": "api",
            "sheets": [],
            "raw_row_count": len(items),
            "parsed_row_count": 0,
        }
        result.manifest["files"].append(source_manifest)
        result.manifest["raw_row_count"] += len(items)

        if not items:
            result.issues.append(
                ValidationIssue(
                    severity="warning",
                    code="API_MONTH_EMPTY",
                    message=f"{month}未返回计费项明细",
                )
            )
            return

        headers = set()
        for item in items:
            headers.update(item.keys())
        headers.add("BillingCycle")
        mapping = build_header_mapping(headers)
        if "item_code" not in mapping and "BillingItem" in headers:
            mapping["item_code"] = "BillingItem"
        if "item_name" not in mapping and "BillingItem" in headers:
            mapping["item_name"] = "BillingItem"

        parsed = 0
        for index, item in enumerate(items, start=1):
            raw = dict(item)
            raw.setdefault("BillingCycle", month)
            try:
                record = map_row_to_record(
                    raw,
                    mapping,
                    source_file=source_name,
                    source_file_sha256=response_hash,
                    source_sheet="API",
                    source_row=index,
                    billing_type_mapper=self.billing_type_mapper,
                )
                result.records.append(record)
                parsed += 1
            except Exception as exc:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="API_ROW_PARSE_FAILED",
                        message=f"{month}第{index}条API记录解析失败: {exc}",
                        samples=[f"{source_name}:{index}"],
                    )
                )
        source_manifest["parsed_row_count"] = parsed

    def _reconcile_overview(
        self,
        month: str,
        items: List[Dict[str, Any]],
        result: ImportResult,
        *,
        product_code: Optional[str],
        bill_owner_id: Optional[str],
    ) -> None:
        response = self.client.query_bill_overview(
            billing_cycle=month,
            product_code=product_code,
            bill_owner_id=bill_owner_id,
        )
        if response.get("Code") != "Success":
            result.issues.append(
                ValidationIssue(
                    severity="warning",
                    code="API_OVERVIEW_UNAVAILABLE",
                    message=(
                        f"{month}产品汇总接口校验不可用: "
                        f"{response.get('Message', response.get('Code', '未知错误'))}"
                    ),
                )
            )
            return
        overview_raw = response.get("Data", {}).get("Items", [])
        if isinstance(overview_raw, dict):
            overview_items = overview_raw.get("Item", [])
        elif isinstance(overview_raw, list):
            overview_items = overview_raw
        else:
            overview_items = []
        if isinstance(overview_items, dict):
            overview_items = [overview_items]
        try:
            detail_total = sum(
                (
                    parse_decimal(item.get("PretaxAmount"), required=True)
                    or Decimal("0")
                    for item in items
                ),
                Decimal("0"),
            )
            overview_total = sum(
                (
                    parse_decimal(item.get("PretaxAmount"), required=True)
                    or Decimal("0")
                    for item in overview_items
                ),
                Decimal("0"),
            )
        except ValueError as exc:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="API_OVERVIEW_PARSE_FAILED",
                    message=f"{month}产品汇总金额解析失败: {exc}",
                )
            )
            return
        result.manifest.setdefault("api_overview_checks", []).append(
            {
                "month": month,
                "split_item_total": str(detail_total),
                "overview_total": str(overview_total),
                "difference": str(detail_total - overview_total),
            }
        )
        if detail_total != overview_total:
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="API_OVERVIEW_MISMATCH",
                    message=(
                        f"{month}计费项明细合计 {detail_total} 与产品汇总 "
                        f"{overview_total} 不一致"
                    ),
                )
            )
