#!/usr/bin/env python3
"""Validation gates for imported bill records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bill_models import (
    OTHER,
    PAY_AS_YOU_GO,
    BillRecord,
    ImportResult,
    ValidationIssue,
    ValidationResult,
    decimal_text,
)


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    count: int = 1,
    samples: Optional[Iterable[str]] = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        count=count,
        samples=list(samples or [])[:10],
    )


def validate_import(
    imported: ImportResult,
    *,
    expected_months: Optional[Sequence[str]] = None,
    allow_multiple_accounts: bool = False,
) -> ValidationResult:
    errors = [
        issue for issue in imported.issues if issue.severity.lower() == "error"
    ]
    warnings = [
        issue for issue in imported.issues if issue.severity.lower() != "error"
    ]
    records = list(imported.records)

    raw_count = int(imported.manifest.get("raw_row_count", 0))
    if raw_count != len(records):
        errors.append(
            _issue(
                "error",
                "ROW_COUNT_MISMATCH",
                f"原始非空数据行数 {raw_count} 与成功解析行数 {len(records)} 不一致",
                count=abs(raw_count - len(records)),
            )
        )

    missing_core: Dict[str, List[str]] = defaultdict(list)
    usage_both_missing: List[str] = []
    usage_pair_mismatch: List[str] = []
    negative_rows: List[str] = []
    zero_rows: List[str] = []
    unknown_type_rows: List[str] = []
    reconciliation_errors: List[str] = []
    reconciliation_checked = 0

    for record in records:
        locator = _locator(record)
        if not record.billing_month:
            missing_core["billing_month"].append(locator)
        if not record.product_code:
            missing_core["product_code"].append(locator)
        if not record.product_name:
            missing_core["product_name"].append(locator)
        if record.billing_type == PAY_AS_YOU_GO:
            if not record.item_code:
                missing_core["item_code"].append(locator)
            if not record.item_name:
                missing_core["item_name"].append(locator)

        if record.usage is None and not record.usage_unit:
            usage_both_missing.append(locator)
        elif (record.usage is None) != (not record.usage_unit):
            usage_pair_mismatch.append(locator)

        if record.payable_amount < 0:
            negative_rows.append(locator)
        elif record.payable_amount == 0:
            zero_rows.append(locator)

        if record.billing_type == OTHER:
            unknown_type_rows.append(
                f"{locator}={record.billing_type_raw or '<空>'}"
            )

        if (
            record.gross_amount is not None
            and record.amount_after_discount is not None
        ):
            reconciliation_checked += 1
            expected_after = (
                record.gross_amount
                - (record.subscription_deduction_gross or Decimal("0"))
                - (record.discount_amount or Decimal("0"))
            )
            expected_payable = (
                record.amount_after_discount
                - (record.coupon_amount or Decimal("0"))
            )
            if (
                expected_after != record.amount_after_discount
                or expected_payable != record.payable_amount
            ):
                reconciliation_errors.append(locator)

    for field_name, locators in sorted(missing_core.items()):
        errors.append(
            _issue(
                "error",
                "REQUIRED_VALUE_MISSING",
                f"必需字段 {field_name} 存在空值",
                count=len(locators),
                samples=locators,
            )
        )

    if usage_pair_mismatch:
        errors.append(
            _issue(
                "error",
                "USAGE_UNIT_MISMATCH",
                "用量和用量单位必须同时有值或同时为空",
                count=len(usage_pair_mismatch),
                samples=usage_pair_mismatch,
            )
        )
    if usage_both_missing:
        warnings.append(
            _issue(
                "warning",
                "USAGE_MISSING",
                "部分记录没有用量及用量单位；金额仍计入，用量不按零处理",
                count=len(usage_both_missing),
                samples=usage_both_missing,
            )
        )
    if negative_rows:
        warnings.append(
            _issue(
                "warning",
                "NEGATIVE_AMOUNT",
                "存在负应付金额记录",
                count=len(negative_rows),
                samples=negative_rows,
            )
        )
    if zero_rows:
        warnings.append(
            _issue(
                "warning",
                "ZERO_AMOUNT",
                "存在零应付金额记录",
                count=len(zero_rows),
                samples=zero_rows,
            )
        )
    if unknown_type_rows:
        warnings.append(
            _issue(
                "warning",
                "UNKNOWN_BILLING_TYPE",
                "存在未映射费用类型，已归入 Other",
                count=len(unknown_type_rows),
                samples=unknown_type_rows,
            )
        )
    if reconciliation_errors:
        errors.append(
            _issue(
                "error",
                "AMOUNT_RECONCILIATION_FAILED",
                "目录总价、优惠后金额和应付金额勾稽失败",
                count=len(reconciliation_errors),
                samples=reconciliation_errors,
            )
        )
    elif reconciliation_checked == 0:
        warnings.append(
            _issue(
                "warning",
                "AMOUNT_RECONCILIATION_UNAVAILABLE",
                "源数据缺少完整金额勾稽字段，仅校验应付金额解析和多维汇总",
            )
        )

    deduped, duplicate_errors, duplicate_warnings, duplicate_count = (
        _deduplicate_records(records)
    )
    errors.extend(duplicate_errors)
    warnings.extend(duplicate_warnings)

    months = sorted({record.billing_month for record in deduped})
    if expected_months:
        missing_months = sorted(set(expected_months) - set(months))
        unexpected_months = sorted(set(months) - set(expected_months))
        if missing_months:
            errors.append(
                _issue(
                    "error",
                    "MISSING_MONTHS",
                    f"缺少指定账期: {', '.join(missing_months)}",
                    count=len(missing_months),
                    samples=missing_months,
                )
            )
        if unexpected_months:
            errors.append(
                _issue(
                    "error",
                    "UNEXPECTED_MONTHS",
                    f"文件包含指定范围之外的账期: {', '.join(unexpected_months)}",
                    count=len(unexpected_months),
                    samples=unexpected_months,
                )
            )

    current_month = date.today().strftime("%Y-%m")
    if current_month in months:
        warnings.append(
            _issue(
                "warning",
                "CURRENT_MONTH_PARTIAL",
                f"账单包含未结束月份 {current_month}，趋势结论必须标记为部分月份",
            )
        )

    accounts = sorted({record.account_id for record in deduped if record.account_id})
    if len(accounts) > 1 and not allow_multiple_accounts:
        errors.append(
            _issue(
                "error",
                "MULTIPLE_ACCOUNTS",
                "检测到多个资源购买账号；请确认账号范围或使用 --allow-multiple-accounts",
                count=len(accounts),
                samples=accounts,
            )
        )
    elif not accounts:
        warnings.append(
            _issue(
                "warning",
                "ACCOUNT_ID_MISSING",
                "源数据没有可用的资源购买账号ID，无法验证账号范围",
            )
        )

    currencies = sorted({record.currency for record in deduped if record.currency})
    currency_missing = sum(1 for record in deduped if not record.currency)
    if len(currencies) > 1:
        errors.append(
            _issue(
                "error",
                "MULTIPLE_CURRENCIES",
                "检测到多个币种，禁止直接汇总",
                count=len(currencies),
                samples=currencies,
            )
        )
    if currency_missing:
        warnings.append(
            _issue(
                "warning",
                "CURRENCY_MISSING",
                "部分记录缺少币种",
                count=currency_missing,
            )
        )

    name_warnings = _name_conflict_issues(deduped)
    warnings.extend(name_warnings)

    amount_total = sum(
        (record.payable_amount for record in deduped), Decimal("0")
    )
    type_counts = Counter(record.billing_type for record in deduped)
    stats = {
        "raw_row_count": raw_count,
        "parsed_row_count": len(records),
        "validated_row_count": len(deduped),
        "duplicate_row_count": duplicate_count,
        "billing_months": months,
        "accounts": accounts,
        "currencies": currencies,
        "billing_type_counts": dict(sorted(type_counts.items())),
        "product_count": len({record.product_code for record in deduped}),
        "item_count": len(
            {
                (record.product_code, record.item_code)
                for record in deduped
                if record.item_code
            }
        ),
        "payable_amount_total": decimal_text(amount_total),
        "usage_missing_count": len(usage_both_missing),
        "negative_amount_count": len(negative_rows),
        "zero_amount_count": len(zero_rows),
        "amount_reconciliation_checked": reconciliation_checked,
    }
    return ValidationResult(
        records=deduped,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )


def _deduplicate_records(
    records: List[BillRecord],
) -> Tuple[
    List[BillRecord],
    List[ValidationIssue],
    List[ValidationIssue],
    int,
]:
    seen_ids: Dict[Tuple[str, str], BillRecord] = {}
    missing_hashes: Dict[str, List[str]] = defaultdict(list)
    deduped: List[BillRecord] = []
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    exact_duplicates: List[str] = []
    conflicts: List[str] = []
    missing_ids: List[str] = []

    for record in records:
        locator = _locator(record)
        if not record.line_item_id:
            missing_ids.append(locator)
            missing_hashes[record.record_hash].append(locator)
            deduped.append(record)
            continue
        key = (record.account_id, record.line_item_id)
        previous = seen_ids.get(key)
        if previous is None:
            seen_ids[key] = record
            deduped.append(record)
        elif previous.record_hash == record.record_hash:
            exact_duplicates.append(locator)
        else:
            conflicts.append(
                f"{_locator(previous)} <-> {locator} / ID={record.line_item_id}"
            )

    if exact_duplicates:
        warnings.append(
            _issue(
                "warning",
                "DUPLICATE_ROWS_REMOVED",
                "相同账号和账单明细ID的完全相同记录已去重",
                count=len(exact_duplicates),
                samples=exact_duplicates,
            )
        )
    if conflicts:
        errors.append(
            _issue(
                "error",
                "LINE_ITEM_ID_CONFLICT",
                "相同账单明细ID对应不同内容",
                count=len(conflicts),
                samples=conflicts,
            )
        )
    if missing_ids:
        warnings.append(
            _issue(
                "warning",
                "LINE_ITEM_ID_MISSING",
                "部分记录缺少账单明细ID，未自动删除内容相同的记录",
                count=len(missing_ids),
                samples=missing_ids,
            )
        )
        possible_duplicates = [
            locators
            for locators in missing_hashes.values()
            if len(locators) > 1
        ]
        if possible_duplicates:
            warnings.append(
                _issue(
                    "warning",
                    "POSSIBLE_DUPLICATES_WITHOUT_ID",
                    "缺少明细ID的记录中存在内容相同项，需要人工确认",
                    count=sum(len(group) for group in possible_duplicates),
                    samples=[
                        " | ".join(group[:3]) for group in possible_duplicates[:10]
                    ],
                )
            )
    return deduped, errors, warnings, len(exact_duplicates)


def _name_conflict_issues(records: List[BillRecord]) -> List[ValidationIssue]:
    product_names: Dict[str, set[str]] = defaultdict(set)
    item_names: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        if record.product_name:
            product_names[record.product_code].add(record.product_name)
        if record.item_name:
            item_names[(record.product_code, record.item_code)].add(record.item_name)

    product_conflicts = [
        f"{code}: {' / '.join(sorted(names))}"
        for code, names in product_names.items()
        if len(names) > 1
    ]
    item_conflicts = [
        f"{product}/{item}: {' / '.join(sorted(names))}"
        for (product, item), names in item_names.items()
        if len(names) > 1
    ]
    issues: List[ValidationIssue] = []
    if product_conflicts:
        issues.append(
            _issue(
                "warning",
                "PRODUCT_NAME_CONFLICT",
                "同一产品Code对应多个产品名称，报告采用出现次数最多的名称",
                count=len(product_conflicts),
                samples=product_conflicts,
            )
        )
    if item_conflicts:
        issues.append(
            _issue(
                "warning",
                "ITEM_NAME_CONFLICT",
                "同一计费项Code对应多个名称，报告采用出现次数最多的名称",
                count=len(item_conflicts),
                samples=item_conflicts,
            )
        )
    return issues


def _locator(record: BillRecord) -> str:
    return f"{record.source_file}:{record.source_sheet}:{record.source_row}"
