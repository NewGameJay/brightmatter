"""Generic adapters for platforms with simpler API patterns.

Covers: Braze, Iterable, Beehiiv, Triple Whale, Amplitude,
        Customer.io, AppsFlyer.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .base import BasePlatformAdapter, DailyMetricRow, PlatformConfig

logger = logging.getLogger(__name__)


def _api_get(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={**headers, "Accept": "application/json"})
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


def _api_post(url: str, headers: Dict[str, str], body: Any) -> Dict[str, Any]:
    data = json.dumps(body).encode() if not isinstance(body, bytes) else body
    req = urllib.request.Request(
        url, data=data,
        headers={**headers, "Accept": "application/json", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


# ── Braze ──────────────────────────────────────────────────────────

class BrazeAdapter(BasePlatformAdapter):
    PLATFORM = "braze"
    RATE_LIMIT_DELAY = 0.2

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        endpoint = config.credentials.get("endpoint", "rest.iad-01.braze.com")
        if not api_key:
            return []
        if not endpoint.startswith("http"):
            endpoint = f"https://{endpoint}"

        headers = {"Authorization": f"Bearer {api_key}"}
        rows: List[DailyMetricRow] = []

        # Braze KPI endpoint gives daily aggregate stats
        try:
            url = (
                f"{endpoint}/kpi/new_users/data_series"
                f"?length=100"
                f"&ending_at={end_date.isoformat()}"
            )
            data = _api_get(url, headers)
            for point in data.get("data", []):
                d = (point.get("time") or "")[:10]
                if d and d >= start_date.isoformat():
                    rows.append(DailyMetricRow(
                        metric_date=date.fromisoformat(d),
                        metrics={"new_users": self._safe_int(point.get("new_users"))},
                        record_count=1,
                    ))
            time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"Braze KPI fetch: {e}")

        # DAU/MAU
        try:
            url = (
                f"{endpoint}/kpi/dau/data_series"
                f"?length=100&ending_at={end_date.isoformat()}"
            )
            data = _api_get(url, headers)
            dau_map = {}
            for point in data.get("data", []):
                d = (point.get("time") or "")[:10]
                if d and d >= start_date.isoformat():
                    dau_map[d] = self._safe_int(point.get("dau"))

            for row in rows:
                d = row.metric_date.isoformat()
                if d in dau_map:
                    row.metrics["dau"] = dau_map[d]
        except Exception as e:
            logger.debug(f"Braze DAU fetch: {e}")

        logger.info(f"Braze: {len(rows)} days for {config.client_name}")
        return rows


# ── Iterable ───────────────────────────────────────────────────────

class IterableAdapter(BasePlatformAdapter):
    PLATFORM = "iterable"
    RATE_LIMIT_DELAY = 0.2

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            return []

        headers = {"Api-Key": api_key}
        rows: List[DailyMetricRow] = []

        # Pull campaign metrics
        try:
            url = "https://api.iterable.com/api/campaigns"
            data = _api_get(url, headers)
            day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"sends": 0, "opens": 0, "clicks": 0, "campaigns": 0}
            )
            for camp in data.get("campaigns", []):
                d = (camp.get("createdAt") or "")[:10]
                if d and start_date.isoformat() <= d <= end_date.isoformat():
                    m = day_metrics[d]
                    m["campaigns"] += 1

            for d, m in sorted(day_metrics.items()):
                rows.append(DailyMetricRow(
                    metric_date=date.fromisoformat(d),
                    metrics=m,
                    record_count=m["campaigns"],
                ))
            time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"Iterable campaigns fetch: {e}")

        logger.info(f"Iterable: {len(rows)} days for {config.client_name}")
        return rows


# ── Beehiiv ────────────────────────────────────────────────────────

class BeehiivAdapter(BasePlatformAdapter):
    PLATFORM = "beehiiv"
    RATE_LIMIT_DELAY = 0.3

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        pub_id = config.credentials.get("publication_id", "")
        if not api_key or not pub_id:
            return []

        headers = {"Authorization": f"Bearer {api_key}"}
        rows: List[DailyMetricRow] = []

        # Pull subscriber growth
        try:
            url = (
                f"https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions"
                f"?limit=100&status=active"
            )
            data = _api_get(url, headers)
            day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"new_subscribers": 0}
            )
            for sub in data.get("data", []):
                d = (sub.get("created") or "")[:10]
                if d and start_date.isoformat() <= d <= end_date.isoformat():
                    day_metrics[d]["new_subscribers"] += 1

            for d, m in sorted(day_metrics.items()):
                rows.append(DailyMetricRow(
                    metric_date=date.fromisoformat(d),
                    metrics=m,
                    record_count=m["new_subscribers"],
                ))
        except Exception as e:
            logger.warning(f"Beehiiv fetch: {e}")

        logger.info(f"Beehiiv: {len(rows)} days for {config.client_name}")
        return rows


# ── Triple Whale ───────────────────────────────────────────────────

class TripleWhaleAdapter(BasePlatformAdapter):
    PLATFORM = "triple_whale"
    RATE_LIMIT_DELAY = 0.3

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        shop = config.credentials.get("shop", "")
        if not api_key:
            return []

        headers = {"x-api-key": api_key}
        rows: List[DailyMetricRow] = []

        try:
            url = (
                f"https://api.triplewhale.com/api/v2/summary-page/summary"
                f"?start={start_date.isoformat()}"
                f"&end={end_date.isoformat()}"
                f"&period=day"
            )
            if shop:
                url += f"&shopDomain={shop}"

            data = _api_get(url, headers)
            for point in data.get("data", data.get("summary", [])):
                d = (point.get("date") or point.get("day") or "")[:10]
                if not d:
                    continue
                rows.append(DailyMetricRow(
                    metric_date=date.fromisoformat(d),
                    metrics={
                        "revenue": self._safe_float(point.get("totalSales") or point.get("revenue")),
                        "orders": self._safe_int(point.get("totalOrders") or point.get("orders")),
                        "ad_spend": self._safe_float(point.get("adSpend") or point.get("totalAdSpend")),
                        "roas": self._safe_float(point.get("blendedRoas") or point.get("roas")),
                        "new_customers": self._safe_int(point.get("newCustomers")),
                        "aov": self._safe_float(point.get("aov")),
                    },
                    record_count=1,
                ))
            time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"TripleWhale fetch: {e}")

        logger.info(f"TripleWhale: {len(rows)} days for {config.client_name}")
        return rows


# ── Amplitude ──────────────────────────────────────────────────────

class AmplitudeAdapter(BasePlatformAdapter):
    PLATFORM = "amplitude"
    RATE_LIMIT_DELAY = 0.2

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            return []

        rows: List[DailyMetricRow] = []
        try:
            # Active/new user counts
            url = (
                f"https://amplitude.com/api/2/users"
                f"?start={start_date.strftime('%Y%m%d')}"
                f"&end={end_date.strftime('%Y%m%d')}"
            )
            data = _api_get(url, {"Authorization": f"Api-Key {api_key}"})
            series = data.get("data", {}).get("series", [[]])
            dates = data.get("data", {}).get("xValues", [])

            for i, d_str in enumerate(dates):
                d = d_str[:10] if len(d_str) >= 10 else d_str
                try:
                    md = date.fromisoformat(d)
                except ValueError:
                    continue
                active = series[0][i] if i < len(series[0]) else 0
                new = series[1][i] if len(series) > 1 and i < len(series[1]) else 0
                rows.append(DailyMetricRow(
                    metric_date=md,
                    metrics={"active_users": self._safe_int(active),
                             "new_users": self._safe_int(new)},
                    record_count=1,
                ))
        except Exception as e:
            logger.warning(f"Amplitude fetch: {e}")

        logger.info(f"Amplitude: {len(rows)} days for {config.client_name}")
        return rows


# ── Customer.io ────────────────────────────────────────────────────

class CustomerIOAdapter(BasePlatformAdapter):
    PLATFORM = "customerio"
    RATE_LIMIT_DELAY = 0.2

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            return []

        base_url = config.credentials.get("base_url", "https://api.customer.io/v1")
        headers = {"Authorization": f"Bearer {api_key}"}
        rows: List[DailyMetricRow] = []

        try:
            url = f"{base_url}/campaigns?page=1&per_page=100"
            data = _api_get(url, headers)
            day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"campaigns": 0, "sends": 0}
            )
            for camp in data.get("campaigns", []):
                d = (camp.get("created") or "")[:10]
                if d and start_date.isoformat() <= d <= end_date.isoformat():
                    day_metrics[d]["campaigns"] += 1

            for d, m in sorted(day_metrics.items()):
                rows.append(DailyMetricRow(
                    metric_date=date.fromisoformat(d),
                    metrics=m,
                    record_count=m["campaigns"],
                ))
        except Exception as e:
            logger.warning(f"CustomerIO fetch: {e}")

        logger.info(f"CustomerIO: {len(rows)} days for {config.client_name}")
        return rows


# ── AppsFlyer ──────────────────────────────────────────────────────

class AppsFlyerAdapter(BasePlatformAdapter):
    PLATFORM = "appsflyer"
    RATE_LIMIT_DELAY = 0.3

    def pull_daily_metrics(
        self, config: PlatformConfig, start_date: date, end_date: date,
    ) -> List[DailyMetricRow]:
        api_key = config.credentials.get("api_key", "")
        app_id = config.credentials.get("app_id", "")
        if not api_key or not app_id:
            return []

        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        rows: List[DailyMetricRow] = []

        try:
            url = (
                f"https://hq1.appsflyer.com/api/agg-data/export/app/{app_id}/partners_report/v5"
                f"?from={start_date.isoformat()}&to={end_date.isoformat()}"
                f"&groupings=date"
            )
            data = _api_get(url, headers)
            for row_data in data if isinstance(data, list) else data.get("data", []):
                d = (row_data.get("date") or "")[:10]
                if not d:
                    continue
                rows.append(DailyMetricRow(
                    metric_date=date.fromisoformat(d),
                    metrics={
                        "installs": self._safe_int(row_data.get("installs")),
                        "impressions": self._safe_int(row_data.get("impressions")),
                        "clicks": self._safe_int(row_data.get("clicks")),
                        "cost": self._safe_float(row_data.get("cost")),
                        "revenue": self._safe_float(row_data.get("revenue")),
                    },
                    record_count=1,
                ))
        except Exception as e:
            logger.warning(f"AppsFlyer fetch: {e}")

        logger.info(f"AppsFlyer: {len(rows)} days for {config.client_name}")
        return rows


# ── Adapter Registry ───────────────────────────────────────────────

ADAPTER_REGISTRY: Dict[str, type] = {
    "braze": BrazeAdapter,
    "iterable": IterableAdapter,
    "beehiiv": BeehiivAdapter,
    "triple_whale": TripleWhaleAdapter,
    "amplitude": AmplitudeAdapter,
    "customerio": CustomerIOAdapter,
    "appsflyer": AppsFlyerAdapter,
}
