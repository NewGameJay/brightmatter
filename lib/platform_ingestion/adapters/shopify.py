"""Shopify adapter — daily order and revenue metrics."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from .base import BasePlatformAdapter, DailyMetricRow, PlatformConfig

logger = logging.getLogger(__name__)


class ShopifyAdapter(BasePlatformAdapter):
    PLATFORM = "shopify"
    RATE_LIMIT_DELAY = 0.5
    MAX_LOOKBACK_DAYS = 1095

    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        token = config.credentials.get("access_token", "")
        store_url = config.credentials.get("store_url", "").rstrip("/")
        if not token or not store_url:
            return []

        if not store_url.startswith("http"):
            store_url = f"https://{store_url}"

        api_version = config.extra.get("api_version", "2024-01")

        day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"orders": 0, "revenue": 0.0, "items_sold": 0,
                     "avg_order_value": 0.0, "refunds": 0, "refund_amount": 0.0}
        )

        # Fetch orders in chunks (Shopify paginates to 250 per page)
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(chunk_start + timedelta(days=29), end_date)

            page_url = (
                f"{store_url}/admin/api/{api_version}/orders.json"
                f"?status=any&limit=250"
                f"&created_at_min={chunk_start.isoformat()}T00:00:00Z"
                f"&created_at_max={chunk_end.isoformat()}T23:59:59Z"
                f"&fields=id,created_at,total_price,line_items,financial_status"
            )

            try:
                while page_url:
                    req = urllib.request.Request(page_url, headers={
                        "X-Shopify-Access-Token": token,
                        "Accept": "application/json",
                    })
                    resp = urllib.request.urlopen(req, timeout=60)
                    data = json.loads(resp.read())

                    for order in data.get("orders", []):
                        d = (order.get("created_at") or "")[:10]
                        if not d:
                            continue
                        m = day_metrics[d]
                        m["orders"] += 1
                        m["revenue"] += self._safe_float(order.get("total_price"))
                        items = order.get("line_items") or []
                        m["items_sold"] += sum(
                            self._safe_int(li.get("quantity")) for li in items
                        )
                        fin = (order.get("financial_status") or "").lower()
                        if fin in ("refunded", "partially_refunded"):
                            m["refunds"] += 1

                    # Link header pagination
                    link_header = resp.headers.get("Link", "")
                    page_url = None
                    if 'rel="next"' in link_header:
                        for part in link_header.split(","):
                            if 'rel="next"' in part:
                                page_url = part.split(";")[0].strip().strip("<>")
                                break

                    time.sleep(self.RATE_LIMIT_DELAY)
            except Exception as e:
                logger.error(f"Shopify orders fetch: {e}")

            chunk_start = chunk_end + timedelta(days=1)

        # Compute AOV
        for m in day_metrics.values():
            if m["orders"] > 0:
                m["avg_order_value"] = round(m["revenue"] / m["orders"], 2)

        rows = [
            DailyMetricRow(
                metric_date=date.fromisoformat(d),
                metrics=dict(m),
                record_count=m["orders"],
            )
            for d, m in sorted(day_metrics.items())
            if m["orders"] > 0
        ]
        logger.info(f"Shopify: {len(rows)} days for {config.client_name}")
        return rows
