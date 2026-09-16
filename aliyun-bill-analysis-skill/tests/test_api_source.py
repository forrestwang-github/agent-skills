from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bill_sources import BSSBillSource
from bill_validator import validate_import


class FakeClient:
    def fetch_all_split_items(self, billing_cycle, **_kwargs):
        return (
            [
                {
                    "BillingCycle": billing_cycle,
                    "SubscriptionType": "PayAsYouGo",
                    "ProductCode": "oss",
                    "ProductName": "对象存储OSS",
                    "BillingItemCode": "traffic",
                    "BillingItem": "外网流出流量",
                    "PretaxAmount": "12.34",
                    "Usage": "7",
                    "UsageUnit": "GB",
                    "Region": "华东1（杭州）",
                    "BillID": f"id-{billing_cycle}",
                    "AccountID": "10001",
                    "Currency": "CNY",
                }
            ],
            "",
        )

    def query_bill_overview(self, billing_cycle, **_kwargs):
        return {
            "Code": "Success",
            "Data": {
                "Items": {
                    "Item": [
                        {
                            "BillingCycle": billing_cycle,
                            "ProductCode": "oss",
                            "PretaxAmount": "12.34",
                        }
                    ]
                }
            },
        }


class ApiSourceTests(unittest.TestCase):
    def test_api_records_use_standard_model(self):
        source = BSSBillSource("test-ak", "test-sk")
        source.client = FakeClient()
        imported = source.fetch(["2026-01", "2026-02"])
        validation = validate_import(
            imported, expected_months=["2026-01", "2026-02"]
        )
        self.assertTrue(validation.passed, validation.to_dict())
        self.assertEqual(2, len(validation.records))
        self.assertEqual(
            "24.68", validation.stats["payable_amount_total"]
        )


if __name__ == "__main__":
    unittest.main()
