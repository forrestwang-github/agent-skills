#!/usr/bin/env python3
"""Versioned field mapping and deterministic value normalization."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from bill_models import (
    OTHER,
    PAY_AS_YOU_GO,
    SUBSCRIPTION,
    BillRecord,
)


SCHEMA_VERSION = "aliyun-consume-detail-v2.1"
PARSER_VERSION = "2.0.0"

FIELD_ALIASES: Dict[str, list[str]] = {
    "billing_month": [
        "账单信息/账单月份",
        "账单月份",
        "账期",
        "BillingCycle",
    ],
    "billing_type_raw": [
        "账单信息/费用类型",
        "费用类型",
        "SubscriptionType",
    ],
    "transaction_type": [
        "账单信息/交易类型",
        "交易类型",
        "TransactionType",
    ],
    "product_code": [
        "产品信息/产品Code",
        "产品Code",
        "ProductCode",
    ],
    "product_name": [
        "产品信息/产品名称",
        "产品名称",
        "ProductName",
        "ProductType",
    ],
    "item_code": [
        "产品信息/计费项Code",
        "计费项Code",
        "BillingItemCode",
    ],
    "item_name": [
        "产品信息/计费项名称",
        "计费项名称",
        "计费项",
        "BillingItem",
        "BillingItemName",
    ],
    "region_code": [
        "资源信息/地域Code",
        "地域Code",
        "RegionCode",
    ],
    "region_name": [
        "资源信息/地域",
        "地域",
        "Region",
    ],
    "payable_amount": [
        "应付信息/应付金额（含税）",
        "应付金额（含税）",
        "应付金额",
        "PretaxAmount",
    ],
    "usage": [
        "用量信息/用量",
        "用量",
        "Usage",
    ],
    "usage_unit": [
        "用量信息/用量单位",
        "用量单位",
        "UsageUnit",
    ],
    "line_item_id": [
        "标识信息/账单明细ID",
        "账单明细ID",
        "BillDetailId",
        "BillID",
        "ItemID",
    ],
    "account_id": [
        "身份信息/资源购买账号ID",
        "资源购买账号ID",
        "BillAccountID",
        "BillOwnerID",
        "AccountID",
    ],
    "currency": [
        "定价信息/定价币种",
        "币种",
        "Currency",
    ],
    "gross_amount": [
        "费用信息/目录总价",
        "目录总价",
        "PretaxGrossAmount",
    ],
    "subscription_deduction_gross": [
        "订阅抵扣信息/订阅抵扣目录总价",
        "订阅抵扣目录总价",
    ],
    "discount_amount": [
        "优惠信息/优惠金额",
        "优惠金额",
        "InvoiceDiscount",
    ],
    "coupon_amount": [
        "优惠券抵扣信息/优惠券抵扣金额",
        "优惠券抵扣金额",
        "DeductedByCoupons",
    ],
    "amount_after_discount": [
        "优惠信息/优惠后金额",
        "优惠后金额",
    ],
}


def _apply_reference_schema() -> None:
    path = Path(__file__).resolve().parent.parent / "references" / "bill-schema-v2.json"
    if not path.exists():
        return
    schema = json.loads(path.read_text(encoding="utf-8"))
    for section_name in (
        "analysis_fields",
        "optional_dimensions",
        "validation_fields",
    ):
        for standard_name, definition in schema.get(section_name, {}).items():
            source = (
                definition.get("source")
                if isinstance(definition, dict)
                else definition
            )
            if source and source not in FIELD_ALIASES.get(standard_name, []):
                FIELD_ALIASES.setdefault(standard_name, []).insert(0, source)


_apply_reference_schema()

REQUIRED_HEADER_KEYS = {
    "billing_month",
    "billing_type_raw",
    "product_code",
    "product_name",
    "item_code",
    "item_name",
    "payable_amount",
    "usage",
    "usage_unit",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return text.replace("\u00a0", " ").strip(" \t\r\n")


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value)).lower()


def build_header_mapping(headers: Iterable[Any]) -> Dict[str, str]:
    normalized_to_actual: Dict[str, str] = {}
    for header in headers:
        actual = clean_text(header)
        if actual:
            normalized_to_actual[normalize_header(actual)] = actual

    mapping: Dict[str, str] = {}
    for standard_name, aliases in FIELD_ALIASES.items():
        matches = {
            normalized_to_actual[normalize_header(alias)]
            for alias in aliases
            if normalize_header(alias) in normalized_to_actual
        }
        if len(matches) > 1:
            raise ValueError(
                f"字段冲突：{standard_name} 同时匹配 {sorted(matches)}"
            )
        if matches:
            mapping[standard_name] = next(iter(matches))
    return mapping


def missing_required_headers(mapping: Mapping[str, str]) -> list[str]:
    return sorted(REQUIRED_HEADER_KEYS - set(mapping))


def parse_decimal(value: Any, *, required: bool = False) -> Optional[Decimal]:
    if value is None or clean_text(value) == "":
        if required:
            raise ValueError("必需数值为空")
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError(f"布尔值不是合法数值: {value}")
    text = clean_text(value).replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"无法解析数值: {value!r}") from exc


def normalize_month(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    text = clean_text(value)
    match = re.fullmatch(r"(\d{4})[-/]?(\d{2})", text)
    if not match:
        raise ValueError(f"无法解析账单月份: {value!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"账单月份非法: {value!r}")
    return f"{year:04d}-{month:02d}"


class BillingTypeMapper:
    def __init__(self, mapping_path: Optional[Path] = None):
        mapping = {
            "云资源按量费用": PAY_AS_YOU_GO,
            "订阅预付费用": SUBSCRIPTION,
            "PayAsYouGo": PAY_AS_YOU_GO,
            "Subscription": SUBSCRIPTION,
            "按量付费": PAY_AS_YOU_GO,
            "后付费": PAY_AS_YOU_GO,
            "包年包月": SUBSCRIPTION,
        }
        if mapping_path and mapping_path.exists():
            loaded = json.loads(mapping_path.read_text(encoding="utf-8"))
            mapping.update(loaded.get("mapping", loaded))
        self.mapping = {clean_text(k): clean_text(v) for k, v in mapping.items()}

    def map(self, raw_value: Any) -> str:
        raw = clean_text(raw_value)
        return self.mapping.get(raw, OTHER)


def _get(raw: Mapping[str, Any], mapping: Mapping[str, str], key: str) -> Any:
    source_key = mapping.get(key)
    return raw.get(source_key) if source_key else None


def map_row_to_record(
    raw: Mapping[str, Any],
    mapping: Mapping[str, str],
    *,
    source_file: str,
    source_file_sha256: str,
    source_sheet: str,
    source_row: int,
    billing_type_mapper: BillingTypeMapper,
) -> BillRecord:
    raw_type = clean_text(_get(raw, mapping, "billing_type_raw"))
    record = BillRecord(
        billing_month=normalize_month(_get(raw, mapping, "billing_month")),
        billing_type=billing_type_mapper.map(raw_type),
        billing_type_raw=raw_type,
        product_code=clean_text(_get(raw, mapping, "product_code")).lower(),
        product_name=clean_text(_get(raw, mapping, "product_name")),
        item_code=clean_text(_get(raw, mapping, "item_code")).lower(),
        item_name=clean_text(_get(raw, mapping, "item_name")),
        payable_amount=parse_decimal(
            _get(raw, mapping, "payable_amount"), required=True
        )
        or Decimal("0"),
        usage=parse_decimal(_get(raw, mapping, "usage")),
        usage_unit=clean_text(_get(raw, mapping, "usage_unit")),
        region_code=clean_text(_get(raw, mapping, "region_code")).lower(),
        region_name=clean_text(_get(raw, mapping, "region_name")),
        transaction_type=clean_text(_get(raw, mapping, "transaction_type")),
        line_item_id=clean_text(_get(raw, mapping, "line_item_id")),
        account_id=clean_text(_get(raw, mapping, "account_id")),
        currency=clean_text(_get(raw, mapping, "currency")).upper(),
        source_file=source_file,
        source_file_sha256=source_file_sha256,
        source_sheet=source_sheet,
        source_row=source_row,
        schema_version=SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        gross_amount=parse_decimal(_get(raw, mapping, "gross_amount")),
        subscription_deduction_gross=parse_decimal(
            _get(raw, mapping, "subscription_deduction_gross")
        ),
        discount_amount=parse_decimal(_get(raw, mapping, "discount_amount")),
        coupon_amount=parse_decimal(_get(raw, mapping, "coupon_amount")),
        amount_after_discount=parse_decimal(
            _get(raw, mapping, "amount_after_discount")
        ),
    )
    record.ensure_record_hash()
    return record
