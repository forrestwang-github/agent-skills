#!/usr/bin/env python3
"""Exact Decimal aggregation and independent SQLite cross-checks."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bill_models import (
    OTHER,
    PAY_AS_YOU_GO,
    SUBSCRIPTION,
    AnalysisResult,
    BillRecord,
    ValidationResult,
    decimal_text,
)


TYPE_DISPLAY = {
    SUBSCRIPTION: "包年包月",
    PAY_AS_YOU_GO: "后付费",
    OTHER: "其他",
}
TYPE_ORDER = {SUBSCRIPTION: 0, PAY_AS_YOU_GO: 1, OTHER: 2}


def analyze_records(
    validation: ValidationResult,
    *,
    customer_name: str = "",
    group_by_region: bool = True,
    top_n: int = 10,
) -> AnalysisResult:
    if not validation.passed:
        raise ValueError("数据校验未通过，不能生成分析结果")
    records = validation.records
    if not records:
        raise ValueError("没有可分析的账单记录")

    months = sorted({record.billing_month for record in records})
    product_names = _preferred_product_names(records)
    item_names = _preferred_item_names(records)

    product_amounts: Dict[Tuple[str, str, str], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    item_amounts: Dict[
        Tuple[str, str, str, str, str, str], Decimal
    ] = defaultdict(lambda: Decimal("0"))
    item_usages: Dict[
        Tuple[str, str, str, str, str, str], Decimal
    ] = defaultdict(lambda: Decimal("0"))
    item_usage_present: set[Tuple[str, str, str, str, str, str]] = set()
    monthly_total: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    billing_type_monthly: Dict[Tuple[str, str], Decimal] = defaultdict(
        lambda: Decimal("0")
    )

    for record in records:
        product_key = (
            record.billing_type,
            record.product_code,
            record.billing_month,
        )
        product_amounts[product_key] += record.payable_amount
        monthly_total[record.billing_month] += record.payable_amount
        billing_type_monthly[
            (record.billing_type, record.billing_month)
        ] += record.payable_amount

        if record.billing_type == PAY_AS_YOU_GO:
            region_code = record.region_code if group_by_region else ""
            region_name = record.region_name if group_by_region else ""
            item_key = (
                record.product_code,
                record.item_code,
                region_code,
                region_name,
                record.usage_unit,
                record.billing_month,
            )
            item_amounts[item_key] += record.payable_amount
            if record.usage is not None:
                item_usages[item_key] += record.usage
                item_usage_present.add(item_key)

    product_rows = _build_product_rows(
        product_amounts, product_names, months
    )
    item_rows = _build_item_rows(
        item_amounts,
        item_usages,
        item_usage_present,
        product_names,
        item_names,
        months,
    )
    total_amount = sum(monthly_total.values(), Decimal("0"))
    postpaid_total = sum(
        (
            value
            for (billing_type, _month), value in billing_type_monthly.items()
            if billing_type == PAY_AS_YOU_GO
        ),
        Decimal("0"),
    )

    data: Dict[str, Any] = {
        "schema_version": "analysis-result-v2",
        "customer_name": customer_name,
        "months": months,
        "group_by_region": group_by_region,
        "top_n": top_n,
        "currencies": validation.stats.get("currencies", []),
        "totals": {
            "payable_amount": decimal_text(total_amount),
            "postpaid_amount": decimal_text(postpaid_total),
            "record_count": len(records),
            "product_count": len({record.product_code for record in records}),
            "postpaid_item_group_count": len(item_rows),
        },
        "monthly_total": {
            month: decimal_text(monthly_total[month]) for month in months
        },
        "billing_type_monthly": {
            billing_type: {
                month: decimal_text(
                    billing_type_monthly[(billing_type, month)]
                )
                for month in months
            }
            for billing_type in (SUBSCRIPTION, PAY_AS_YOU_GO, OTHER)
        },
        "product_rows": product_rows,
        "postpaid_item_rows": item_rows,
        "validation_summary": validation.to_dict(),
    }

    _verify_with_sqlite(records, data, group_by_region=group_by_region)
    data["verification"] = {
        "sqlite_cross_check": "passed",
        "checked_dimensions": [
            "total",
            "month",
            "billing_type_product_month",
            "postpaid_item_region_unit_month",
        ],
    }
    return AnalysisResult(data=data)


def _preferred_product_names(records: Iterable[BillRecord]) -> Dict[str, str]:
    counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.product_name:
            counts[record.product_code][record.product_name] += 1
    return {
        code: counter.most_common(1)[0][0] if counter else code
        for code, counter in counts.items()
    }


def _preferred_item_names(
    records: Iterable[BillRecord],
) -> Dict[Tuple[str, str], str]:
    counts: Dict[Tuple[str, str], Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.item_name:
            counts[(record.product_code, record.item_code)][record.item_name] += 1
    return {
        key: counter.most_common(1)[0][0] if counter else key[1]
        for key, counter in counts.items()
    }


def _build_product_rows(
    amounts: Dict[Tuple[str, str, str], Decimal],
    product_names: Dict[str, str],
    months: List[str],
) -> List[Dict[str, Any]]:
    keys = {(billing_type, product) for billing_type, product, _ in amounts}
    rows: List[Dict[str, Any]] = []
    for billing_type, product_code in keys:
        monthly = {
            month: amounts[(billing_type, product_code, month)]
            for month in months
        }
        total = sum(monthly.values(), Decimal("0"))
        rows.append(
            {
                "billing_type": billing_type,
                "billing_type_display": TYPE_DISPLAY.get(
                    billing_type, billing_type
                ),
                "product_code": product_code,
                "product_name": product_names.get(product_code, product_code),
                "monthly_amounts": {
                    month: decimal_text(value)
                    for month, value in monthly.items()
                },
                "total_amount": decimal_text(total),
            }
        )
    rows.sort(
        key=lambda row: (
            TYPE_ORDER.get(row["billing_type"], 99),
            -Decimal(row["total_amount"]),
            row["product_code"],
        )
    )
    return rows


def _build_item_rows(
    amounts: Dict[Tuple[str, str, str, str, str, str], Decimal],
    usages: Dict[Tuple[str, str, str, str, str, str], Decimal],
    usage_present: set[Tuple[str, str, str, str, str, str]],
    product_names: Dict[str, str],
    item_names: Dict[Tuple[str, str], str],
    months: List[str],
) -> List[Dict[str, Any]]:
    group_keys = {
        (product, item, region_code, region_name, usage_unit)
        for product, item, region_code, region_name, usage_unit, _ in amounts
    }
    rows: List[Dict[str, Any]] = []
    for product, item, region_code, region_name, usage_unit in group_keys:
        monthly: Dict[str, Dict[str, Optional[str]]] = {}
        total_amount = Decimal("0")
        total_usage = Decimal("0")
        any_usage = False
        for month in months:
            key = (
                product,
                item,
                region_code,
                region_name,
                usage_unit,
                month,
            )
            amount = amounts[key]
            total_amount += amount
            usage_value: Optional[Decimal]
            if key in usage_present:
                usage_value = usages[key]
                total_usage += usage_value
                any_usage = True
            else:
                usage_value = None
            monthly[month] = {
                "usage": decimal_text(usage_value),
                "amount": decimal_text(amount),
            }
        rows.append(
            {
                "product_code": product,
                "product_name": product_names.get(product, product),
                "item_code": item,
                "item_name": item_names.get((product, item), item),
                "region_code": region_code,
                "region_name": region_name,
                "usage_unit": usage_unit,
                "monthly": monthly,
                "total_usage": decimal_text(total_usage) if any_usage else None,
                "total_amount": decimal_text(total_amount),
            }
        )
    rows.sort(
        key=lambda row: (
            -Decimal(row["total_amount"]),
            row["product_code"],
            row["item_code"],
            row["region_code"],
            row["usage_unit"],
        )
    )
    return rows


class _DecimalSum:
    def __init__(self) -> None:
        self.total = Decimal("0")

    def step(self, value: Optional[str]) -> None:
        if value not in (None, ""):
            self.total += Decimal(value)

    def finalize(self) -> str:
        return decimal_text(self.total) or "0"


def _verify_with_sqlite(
    records: List[BillRecord],
    analysis: Dict[str, Any],
    *,
    group_by_region: bool,
) -> None:
    connection = sqlite3.connect(":memory:")
    connection.create_aggregate("DECIMAL_SUM", 1, _DecimalSum)
    try:
        connection.execute(
            """
            CREATE TABLE bill (
                billing_month TEXT,
                billing_type TEXT,
                product_code TEXT,
                item_code TEXT,
                region_code TEXT,
                region_name TEXT,
                usage_unit TEXT,
                amount TEXT,
                usage TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO bill VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    record.billing_month,
                    record.billing_type,
                    record.product_code,
                    record.item_code,
                    record.region_code if group_by_region else "",
                    record.region_name if group_by_region else "",
                    record.usage_unit,
                    decimal_text(record.payable_amount),
                    decimal_text(record.usage),
                )
                for record in records
            ],
        )

        sqlite_total = Decimal(
            connection.execute(
                "SELECT DECIMAL_SUM(amount) FROM bill"
            ).fetchone()[0]
        )
        if sqlite_total != Decimal(analysis["totals"]["payable_amount"]):
            raise ValueError(
                f"SQLite总金额不一致: {sqlite_total} != "
                f"{analysis['totals']['payable_amount']}"
            )

        expected_month = {
            month: Decimal(value)
            for month, value in analysis["monthly_total"].items()
        }
        actual_month = {
            month: Decimal(total)
            for month, total in connection.execute(
                """
                SELECT billing_month, DECIMAL_SUM(amount)
                FROM bill GROUP BY billing_month
                """
            )
        }
        if actual_month != expected_month:
            raise ValueError("SQLite月度金额与Python聚合不一致")

        expected_product = {
            (
                row["billing_type"],
                row["product_code"],
                month,
            ): Decimal(value)
            for row in analysis["product_rows"]
            for month, value in row["monthly_amounts"].items()
            if Decimal(value) != 0
        }
        actual_product = {
            (billing_type, product_code, month): Decimal(total)
            for billing_type, product_code, month, total in connection.execute(
                """
                SELECT billing_type, product_code, billing_month,
                       DECIMAL_SUM(amount)
                FROM bill
                GROUP BY billing_type, product_code, billing_month
                """
            )
            if Decimal(total) != 0
        }
        if actual_product != expected_product:
            raise ValueError("SQLite产品月度金额与Python聚合不一致")

        expected_items_amount: Dict[
            Tuple[str, str, str, str, str, str], Decimal
        ] = {}
        expected_items_usage: Dict[
            Tuple[str, str, str, str, str, str], Decimal
        ] = {}
        for row in analysis["postpaid_item_rows"]:
            for month, cell in row["monthly"].items():
                key = (
                    row["product_code"],
                    row["item_code"],
                    row["region_code"],
                    row["region_name"],
                    row["usage_unit"],
                    month,
                )
                amount = Decimal(cell["amount"])
                if amount != 0:
                    expected_items_amount[key] = amount
                if cell["usage"] is not None:
                    expected_items_usage[key] = Decimal(cell["usage"])

        actual_items_amount = {
            (
                product,
                item,
                region_code,
                region_name,
                unit,
                month,
            ): Decimal(total)
            for (
                product,
                item,
                region_code,
                region_name,
                unit,
                month,
                total,
            ) in connection.execute(
                """
                SELECT product_code, item_code, region_code, region_name,
                       usage_unit, billing_month, DECIMAL_SUM(amount)
                FROM bill
                WHERE billing_type = ?
                GROUP BY product_code, item_code, region_code, region_name,
                         usage_unit, billing_month
                """,
                (PAY_AS_YOU_GO,),
            )
            if Decimal(total) != 0
        }
        if actual_items_amount != expected_items_amount:
            raise ValueError("SQLite后付费计费项金额与Python聚合不一致")

        actual_items_usage = {
            (
                product,
                item,
                region_code,
                region_name,
                unit,
                month,
            ): Decimal(total)
            for (
                product,
                item,
                region_code,
                region_name,
                unit,
                month,
                total,
            ) in connection.execute(
                """
                SELECT product_code, item_code, region_code, region_name,
                       usage_unit, billing_month, DECIMAL_SUM(usage)
                FROM bill
                WHERE billing_type = ? AND usage IS NOT NULL
                GROUP BY product_code, item_code, region_code, region_name,
                         usage_unit, billing_month
                """,
                (PAY_AS_YOU_GO,),
            )
        }
        if actual_items_usage != expected_items_usage:
            raise ValueError("SQLite后付费计费项用量与Python聚合不一致")
    finally:
        connection.close()
