"""Meta (Facebook) Ads adapter using the Marketing API."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List

from .base import BasePlatformAdapter, DailyMetricRow, PlatformConfig

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

INSIGHT_FIELDS = [
    "impressions", "reach", "frequency",
    "clicks", "cpc", "cpm", "ctr",
    "spend", "actions", "action_values",
    "conversions", "conversion_values",
    "cost_per_action_type",
]


def _http_get(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        logger.error(f"Meta API HTTP {e.code}: {body}")
        raise


class MetaAdsAdapter(BasePlatformAdapter):
    PLATFORM = "meta_ads"
    RATE_LIMIT_DELAY = 0.5
    MAX_LOOKBACK_DAYS = 1100  # ~37 months

    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        token = config.credentials.get("access_token", "")
        account_id = str(config.account_id or "")
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        if not token:
            logger.warning(f"MetaAds: no access_token for {config.client_name}")
            return []

        fields_str = ",".join(INSIGHT_FIELDS)
        rows: List[DailyMetricRow] = []

        # Chunk into 90-day windows (Meta limits time_range to ~93 days for daily)
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(chunk_start + timedelta(days=89), end_date)

            time_range = urllib.parse.quote(
                json.dumps({"since": chunk_start.isoformat(), "until": chunk_end.isoformat()})
            )
            url = (
                f"{GRAPH_API_BASE}/{account_id}/insights"
                f"?fields={fields_str}"
                f"&level=account"
                f"&time_range={time_range}"
                f"&time_increment=1"
                f"&limit=500"
                f"&access_token={token}"
            )

            try:
                page_url = url
                while page_url:
                    data = _http_get(page_url)
                    for row in data.get("data", []):
                        d_str = row.get("date_start", "")
                        if not d_str:
                            continue

                        m: Dict[str, Any] = {
                            "spend": self._safe_float(row.get("spend")),
                            "impressions": self._safe_int(row.get("impressions")),
                            "reach": self._safe_int(row.get("reach")),
                            "clicks": self._safe_int(row.get("clicks")),
                            "cpc": self._safe_float(row.get("cpc")),
                            "cpm": self._safe_float(row.get("cpm")),
                            "ctr": self._safe_float(row.get("ctr")),
                            "frequency": self._safe_float(row.get("frequency")),
                        }

                        # Extract conversions from actions array
                        actions = row.get("actions") or []
                        for a in actions:
                            atype = a.get("action_type", "")
                            val = self._safe_float(a.get("value"))
                            if atype == "purchase":
                                m["purchases"] = val
                            elif atype == "lead":
                                m["leads"] = val
                            elif atype == "complete_registration":
                                m["registrations"] = val
                            elif atype == "add_to_cart":
                                m["add_to_cart"] = val
                            elif atype == "link_click":
                                m["link_clicks"] = val

                        # Extract conversion values
                        action_values = row.get("action_values") or []
                        for av in action_values:
                            if av.get("action_type") == "purchase":
                                m["purchase_value"] = self._safe_float(av.get("value"))

                        # Computed metrics
                        if m["spend"] > 0 and m.get("purchase_value", 0) > 0:
                            m["roas"] = round(m["purchase_value"] / m["spend"], 4)
                        if m["spend"] > 0 and m.get("purchases", 0) > 0:
                            m["cost_per_purchase"] = round(m["spend"] / m["purchases"], 2)

                        rows.append(DailyMetricRow(
                            metric_date=date.fromisoformat(d_str),
                            metrics=m,
                            record_count=1,
                        ))

                    page_url = data.get("paging", {}).get("next")
                    if page_url:
                        time.sleep(self.RATE_LIMIT_DELAY)

            except Exception as e:
                logger.error(
                    f"MetaAds failed for {config.client_name} "
                    f"({chunk_start}–{chunk_end}): {e}"
                )

            chunk_start = chunk_end + timedelta(days=1)
            time.sleep(self.RATE_LIMIT_DELAY)

        logger.info(f"MetaAds: {len(rows)} days for {config.client_name}")
        return rows
