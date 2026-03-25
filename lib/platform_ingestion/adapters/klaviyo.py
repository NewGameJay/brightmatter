"""Klaviyo adapter — pulls campaign and flow metrics."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BasePlatformAdapter, DailyMetricRow, PlatformConfig

logger = logging.getLogger(__name__)

KLAVIYO_BASE = "https://a.klaviyo.com/api"
REVISION = "2024-10-15"


def _klaviyo_get(url: str, api_key: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Klaviyo-API-Key {api_key}",
        "Accept": "application/json",
        "revision": REVISION,
    }
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


class KlaviyoAdapter(BasePlatformAdapter):
    PLATFORM = "klaviyo"
    RATE_LIMIT_DELAY = 0.15
    MAX_LOOKBACK_DAYS = 1095

    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            return []

        rows: List[DailyMetricRow] = []

        # Pull campaign send/open/click aggregates by day
        campaign_rows = self._pull_campaigns(api_key, start_date, end_date)
        rows.extend(campaign_rows)

        # Pull flow message stats
        flow_rows = self._pull_flows(api_key, start_date, end_date)
        rows.extend(flow_rows)

        logger.info(f"Klaviyo: {len(rows)} days for {config.client_name}")
        return rows

    def _pull_campaigns(
        self, api_key: str, start_date: date, end_date: date
    ) -> List[DailyMetricRow]:
        """Pull campaigns created within the date range and aggregate by send date."""
        day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"sends": 0, "opens": 0, "clicks": 0, "bounces": 0,
                     "unsubscribes": 0, "revenue": 0.0, "campaigns": 0}
        )

        url: Optional[str] = (
            f"{KLAVIYO_BASE}/campaigns"
            f"?filter=equals(messages.channel,'email')"
            f"&page[size]=50"
        )

        try:
            while url:
                data = _klaviyo_get(url, api_key)
                for camp in data.get("data", []):
                    attrs = camp.get("attributes", {})
                    send_time = attrs.get("send_time") or attrs.get("created_at") or ""
                    if not send_time:
                        continue
                    d = send_time[:10]
                    if d < start_date.isoformat() or d > end_date.isoformat():
                        continue

                    stats = attrs.get("send_options", {})
                    m = day_metrics[d]
                    m["campaigns"] += 1

                # Paginate
                next_link = (data.get("links") or {}).get("next")
                url = next_link if next_link else None
                time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"Klaviyo campaigns fetch error: {e}")

        # Pull metric aggregates (Placed Order, Opened Email, etc.) via metrics endpoint
        try:
            self._aggregate_metric_events(api_key, start_date, end_date, day_metrics)
        except Exception as e:
            logger.warning(f"Klaviyo metric aggregation error: {e}")

        return [
            DailyMetricRow(
                metric_date=date.fromisoformat(d),
                metrics=m,
                record_count=m["campaigns"],
            )
            for d, m in sorted(day_metrics.items())
            if any(v for k, v in m.items() if k != "campaigns")
        ]

    def _aggregate_metric_events(
        self,
        api_key: str,
        start_date: date,
        end_date: date,
        day_metrics: Dict[str, Dict[str, Any]],
    ) -> None:
        """Use the Klaviyo Metrics API to get event counts by day."""
        metric_ids: Dict[str, str] = {}
        url: Optional[str] = f"{KLAVIYO_BASE}/metrics?page[size]=50"
        try:
            while url:
                data = _klaviyo_get(url, api_key)
                for m in data.get("data", []):
                    name = (m.get("attributes", {}).get("name") or "").lower()
                    mid = m.get("id", "")
                    if any(k in name for k in ("opened email", "clicked email",
                                                "received email", "bounced",
                                                "unsubscribed", "placed order",
                                                "ordered product")):
                        metric_ids[name] = mid
                url = (data.get("links") or {}).get("next")
                time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.debug(f"Klaviyo metrics list: {e}")

        # For each key metric, query aggregate timeseries
        for metric_name, metric_id in metric_ids.items():
            try:
                agg_url = (
                    f"{KLAVIYO_BASE}/metric-aggregates"
                )
                body = json.dumps({
                    "data": {
                        "type": "metric-aggregate",
                        "attributes": {
                            "metric_id": metric_id,
                            "measurements": ["count", "sum_value"],
                            "interval": "day",
                            "filter": [
                                f"greater-or-equal(datetime,{start_date.isoformat()}T00:00:00Z)",
                                f"less-than(datetime,{(end_date + timedelta(days=1)).isoformat()}T00:00:00Z)",
                            ],
                        },
                    }
                }).encode()
                headers = {
                    "Authorization": f"Klaviyo-API-Key {api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "revision": REVISION,
                }
                req = urllib.request.Request(agg_url, data=body, headers=headers, method="POST")
                resp = urllib.request.urlopen(req, timeout=60)
                result = json.loads(resp.read())

                dates = result.get("data", {}).get("attributes", {}).get("dates", [])
                counts = result.get("data", {}).get("attributes", {}).get("data", [{}])
                count_values = counts[0].get("measurements", {}).get("count", []) if counts else []
                sum_values = counts[0].get("measurements", {}).get("sum_value", []) if counts else []

                key = "revenue" if "order" in metric_name else metric_name.replace(" ", "_").split("_")[0]

                for i, d_str in enumerate(dates):
                    d = d_str[:10]
                    if i < len(count_values):
                        day_metrics[d][f"{key}_count"] = self._safe_int(count_values[i])
                    if i < len(sum_values) and "order" in metric_name:
                        day_metrics[d]["revenue"] += self._safe_float(sum_values[i])

                time.sleep(self.RATE_LIMIT_DELAY)
            except Exception as e:
                logger.debug(f"Klaviyo aggregate for {metric_name}: {e}")

    def _pull_flows(
        self, api_key: str, start_date: date, end_date: date
    ) -> List[DailyMetricRow]:
        """Pull flow metadata (not per-day stats — Klaviyo flows API is limited)."""
        return []
