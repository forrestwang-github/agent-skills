#!/usr/bin/env python3
"""Shared data models for deterministic bill analysis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


PAY_AS_YOU_GO = "PayAsYouGo"
SUBSCRIPTION = "Subscription"
OTHER = "Other"


def decimal_text(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


@dataclass
class BillRecord:
    billing_month: str
    billing_type: str
    billing_type_raw: str
    product_code: str
    product_name: str
    item_code: str
    item_name: str
    payable_amount: Decimal
    usage: Optional[Decimal] = None
    usage_unit: str = ""
    region_code: str = ""
    region_name: str = ""
    transaction_type: str = ""
    line_item_id: str = ""
    account_id: str = ""
    currency: str = ""
    source_file: str = ""
    source_file_sha256: str = ""
    source_sheet: str = ""
    source_row: int = 0
    record_hash: str = ""
    schema_version: str = ""
    parser_version: str = ""
    gross_amount: Optional[Decimal] = None
    subscription_deduction_gross: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    coupon_amount: Optional[Decimal] = None
    amount_after_discount: Optional[Decimal] = None

    def semantic_payload(self) -> Dict[str, Any]:
        """Return source-independent fields used for duplicate comparison."""
        return {
            "billing_month": self.billing_month,
            "billing_type": self.billing_type,
            "billing_type_raw": self.billing_type_raw,
            "product_code": self.product_code,
            "product_name": self.product_name,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "payable_amount": decimal_text(self.payable_amount),
            "usage": decimal_text(self.usage),
            "usage_unit": self.usage_unit,
            "region_code": self.region_code,
            "region_name": self.region_name,
            "transaction_type": self.transaction_type,
            "line_item_id": self.line_item_id,
            "account_id": self.account_id,
            "currency": self.currency,
            "gross_amount": decimal_text(self.gross_amount),
            "subscription_deduction_gross": decimal_text(
                self.subscription_deduction_gross
            ),
            "discount_amount": decimal_text(self.discount_amount),
            "coupon_amount": decimal_text(self.coupon_amount),
            "amount_after_discount": decimal_text(self.amount_after_discount),
        }

    def ensure_record_hash(self) -> None:
        payload = json.dumps(
            self.semantic_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.record_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in (
            "payable_amount",
            "usage",
            "gross_amount",
            "subscription_deduction_gross",
            "discount_amount",
            "coupon_amount",
            "amount_after_discount",
        ):
            data[key] = decimal_text(getattr(self, key))
        return data


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str
    count: int = 1
    samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImportResult:
    records: List[BillRecord] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)
    issues: List[ValidationIssue] = field(default_factory=list)


@dataclass
class ValidationResult:
    records: List[BillRecord] = field(default_factory=list)
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "passed" if self.passed else "failed",
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "stats": self.stats,
        }


@dataclass
class AnalysisResult:
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return self.data
