#!/usr/bin/env python3
"""Minimal read-only Alibaba Cloud BSS OpenAPI client."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


BSS_ENDPOINT = "https://business.aliyuncs.com/"
API_VERSION = "2017-12-14"


class BSSClient:
    """Call only the read-only bill APIs required by this skill."""

    def __init__(self, ak: str, sk: str):
        if not ak or not sk:
            raise ValueError("AccessKey ID 和 AccessKey Secret 均不能为空")
        self.ak = ak
        self.sk = sk

    @staticmethod
    def _percent_encode(value: Any) -> str:
        return urllib.parse.quote(str(value), safe="")

    def _sign(self, params: Dict[str, Any], method: str) -> str:
        query = "&".join(
            f"{self._percent_encode(key)}={self._percent_encode(value)}"
            for key, value in sorted(params.items())
        )
        string_to_sign = f"{method}&%2F&{self._percent_encode(query)}"
        key = f"{self.sk}&".encode("utf-8")
        digest = hmac.new(
            key, string_to_sign.encode("utf-8"), hashlib.sha1
        ).digest()
        return base64.b64encode(digest).decode("ascii")

    def _call(self, action: str, **params: Any) -> Dict[str, Any]:
        request_params: Dict[str, Any] = {
            "AccessKeyId": self.ak,
            "Action": action,
            "Format": "JSON",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": str(uuid.uuid4()),
            "SignatureVersion": "1.0",
            "Timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "Version": API_VERSION,
        }
        request_params.update(
            {key: value for key, value in params.items() if value is not None}
        )
        encoded = urllib.parse.urlencode(request_params)
        method = "POST" if len(BSS_ENDPOINT) + len(encoded) + 100 > 2000 else "GET"
        request_params["Signature"] = self._sign(request_params, method)

        if method == "POST":
            request = urllib.request.Request(
                BSS_ENDPOINT,
                data=urllib.parse.urlencode(request_params).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
            )
        else:
            request = urllib.request.Request(
                BSS_ENDPOINT + "?" + urllib.parse.urlencode(request_params)
            )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return {
                "Code": f"HTTP{exc.code}",
                "Message": body[:500],
            }
        except Exception as exc:
            return {
                "Code": "NetworkError",
                "Message": str(exc)[:500],
            }

    def query_split_item_bill(
        self,
        billing_cycle: str,
        page_num: int = 1,
        page_size: int = 300,
        granularity: str = "MONTHLY",
        product_code: Optional[str] = None,
        bill_owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._call(
            "QuerySplitItemBill",
            BillingCycle=billing_cycle,
            Granularity=granularity,
            PageNum=page_num,
            PageSize=page_size,
            ProductCode=product_code,
            BillOwnerId=bill_owner_id,
        )

    def query_bill_overview(
        self,
        billing_cycle: str,
        product_code: Optional[str] = None,
        bill_owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._call(
            "QueryBillOverview",
            BillingCycle=billing_cycle,
            ProductCode=product_code,
            BillOwnerId=bill_owner_id,
        )

    def fetch_all_split_items(
        self,
        billing_cycle: str,
        product_code: Optional[str] = None,
        bill_owner_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> Tuple[List[Dict[str, Any]], str]:
        all_items: List[Dict[str, Any]] = []
        page_num = 1
        while True:
            response: Dict[str, Any] = {}
            last_error = ""
            for attempt in range(max_retries):
                response = self.query_split_item_bill(
                    billing_cycle=billing_cycle,
                    page_num=page_num,
                    page_size=300,
                    product_code=product_code,
                    bill_owner_id=bill_owner_id,
                )
                if response.get("Code") == "Success":
                    break
                last_error = str(
                    response.get("Message") or response.get("Code") or "未知错误"
                )
                if attempt < max_retries - 1:
                    time.sleep(attempt + 1)

            if response.get("Code") != "Success":
                return all_items, f"第{page_num}页失败: {last_error}"

            data = response.get("Data", {})
            items = _extract_items(data.get("Items", []))
            all_items.extend(items)
            total_count = int(data.get("TotalCount") or 0)
            if not items or len(all_items) >= total_count:
                break
            page_num += 1
        return all_items, ""


def _extract_items(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("Item", [])
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []
