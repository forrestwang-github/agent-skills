from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bill_importer import BillFileImporter
from bill_validator import validate_import


HEADERS = [
    "标识信息/账单明细ID",
    "身份信息/资源购买账号ID",
    "账单信息/账单月份",
    "账单信息/费用类型",
    "账单信息/交易类型",
    "产品信息/产品Code",
    "产品信息/产品名称",
    "产品信息/计费项Code",
    "产品信息/计费项名称",
    "资源信息/地域Code",
    "资源信息/地域",
    "应付信息/应付金额（含税）",
    "用量信息/用量",
    "用量信息/用量单位",
    "定价信息/定价币种",
]

ROWS = [
    [
        "1",
        "10001",
        "202601",
        "订阅预付费用",
        "新购",
        "ecs",
        "云服务器ECS",
        "instance",
        "云服务器",
        "cn-hangzhou",
        "华东1（杭州）",
        "100.10",
        None,
        None,
        "CNY",
    ],
    [
        "2",
        "10001",
        "202601",
        "云资源按量费用",
        "后付费",
        "oss",
        "对象存储OSS",
        "traffic",
        "外网流出流量",
        "cn-hangzhou",
        "华东1（杭州）",
        "10.005",
        "5",
        "GB",
        "CNY",
    ],
    [
        "3",
        "10001",
        "202602",
        "云资源按量费用",
        "后付费",
        "oss",
        "对象存储OSS",
        "traffic",
        "外网流出流量",
        "cn-hangzhou",
        "华东1（杭州）",
        "-2",
        "1",
        "GB",
        "CNY",
    ],
    [
        "4",
        "10001",
        "202602",
        "云资源按量费用",
        "后付费",
        "oss",
        "对象存储OSS",
        "request",
        "请求次数",
        "cn-hangzhou",
        "华东1（杭州）",
        "3",
        "100",
        "次",
        "CNY",
    ],
]


def create_fixture(path: Path, rows=None) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "账单明细"
    worksheet.append(HEADERS)
    for row in rows or ROWS:
        worksheet.append(row)
    workbook.save(path)


class ImporterValidatorTests(unittest.TestCase):
    def test_import_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bill.xlsx"
            create_fixture(path)
            imported = BillFileImporter().load(path)
            validated = validate_import(
                imported, expected_months=["2026-01", "2026-02"]
            )
            self.assertTrue(validated.passed, validated.to_dict())
            self.assertEqual(4, len(validated.records))
            self.assertEqual("111.105", validated.stats["payable_amount_total"])
            self.assertEqual(1, validated.stats["negative_amount_count"])
            self.assertEqual(1, validated.stats["usage_missing_count"])

    def test_conflicting_line_item_id_blocks(self) -> None:
        rows = [list(row) for row in ROWS]
        conflict = list(ROWS[1])
        conflict[11] = "99"
        rows.append(conflict)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflict.xlsx"
            create_fixture(path, rows)
            imported = BillFileImporter().load(path)
            validated = validate_import(imported)
            self.assertFalse(validated.passed)
            self.assertIn(
                "LINE_ITEM_ID_CONFLICT",
                {issue.code for issue in validated.errors},
            )

    def test_usage_unit_pair_mismatch_blocks(self) -> None:
        rows = [list(row) for row in ROWS]
        rows[1][13] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage-mismatch.xlsx"
            create_fixture(path, rows)
            imported = BillFileImporter().load(path)
            validated = validate_import(imported)
            self.assertFalse(validated.passed)
            self.assertIn(
                "USAGE_UNIT_MISMATCH",
                {issue.code for issue in validated.errors},
            )

    def test_csv_and_zip_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            csv_path = temp / "bill.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerows(ROWS)
            zip_path = temp / "bill.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.write(csv_path, arcname="账单/bill.csv")

            imported = BillFileImporter().load(zip_path)
            validated = validate_import(
                imported, expected_months=["2026-01", "2026-02"]
            )
            self.assertTrue(validated.passed, validated.to_dict())
            self.assertEqual(4, len(validated.records))

    def test_duplicate_files_are_not_double_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            first = temp / "bill-a.xlsx"
            second = temp / "bill-b.xlsx"
            create_fixture(first)
            shutil.copyfile(first, second)

            imported = BillFileImporter().load(temp)
            validated = validate_import(imported)
            self.assertTrue(validated.passed, validated.to_dict())
            self.assertEqual(4, len(validated.records))
            self.assertIn(
                "DUPLICATE_FILE",
                {issue.code for issue in validated.warnings},
            )


if __name__ == "__main__":
    unittest.main()
