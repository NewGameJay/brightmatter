"""HubSpot adapter — contacts, deals, and email campaign metrics."""

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

HUBSPOT_BASE = "https://api.hubapi.com"


def _hs_get(url: str, token: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


class HubSpotAdapter(BasePlatformAdapter):
    PLATFORM = "hubspot"
    RATE_LIMIT_DELAY = 0.12
    MAX_LOOKBACK_DAYS = 1095

    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        token = config.credentials.get("access_token", "")
        if not token:
            return []

        day_metrics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"contacts_created": 0, "deals_created": 0,
                     "deals_closed_won": 0, "revenue": 0.0,
                     "emails_sent": 0, "emails_opened": 0,
                     "emails_clicked": 0}
        )

        self._pull_contacts_by_day(token, start_date, end_date, day_metrics)
        self._pull_deals_by_day(token, start_date, end_date, day_metrics)
        self._pull_email_events(token, start_date, end_date, day_metrics)

        rows = [
            DailyMetricRow(
                metric_date=date.fromisoformat(d),
                metrics=dict(m),
                record_count=m["contacts_created"] + m["deals_created"],
            )
            for d, m in sorted(day_metrics.items())
            if any(v for v in m.values())
        ]
        logger.info(f"HubSpot: {len(rows)} days for {config.client_name}")
        return rows

    def _pull_contacts_by_day(
        self, token: str, start_date: date, end_date: date,
        day_metrics: Dict[str, Dict[str, Any]],
    ) -> None:
        start_ms = int(datetime.combine(start_date, datetime.min.time(),
                                         tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime.combine(end_date + timedelta(days=1),
                                       datetime.min.time(),
                                       tzinfo=timezone.utc).timestamp() * 1000)
        after = None
        fetched = 0
        try:
            while True:
                url = (
                    f"{HUBSPOT_BASE}/crm/v3/objects/contacts"
                    f"?limit=100&properties=createdate"
                    f"&filterGroups=[{{"
                    f'"filters":[{{"propertyName":"createdate","operator":"GTE","value":"{start_ms}"}},'
                    f'{{"propertyName":"createdate","operator":"LTE","value":"{end_ms}"}}]'
                    f"}}]"
                )
                if after:
                    url += f"&after={after}"

                data = _hs_get(url, token)
                for c in data.get("results", []):
                    cd = (c.get("properties", {}).get("createdate") or "")[:10]
                    if cd:
                        day_metrics[cd]["contacts_created"] += 1
                        fetched += 1

                paging = data.get("paging", {}).get("next", {})
                after = paging.get("after")
                if not after or fetched > 10000:
                    break
                time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"HubSpot contacts fetch: {e}")

    def _pull_deals_by_day(
        self, token: str, start_date: date, end_date: date,
        day_metrics: Dict[str, Dict[str, Any]],
    ) -> None:
        after = None
        fetched = 0
        try:
            while True:
                url = (
                    f"{HUBSPOT_BASE}/crm/v3/objects/deals"
                    f"?limit=100&properties=createdate,closedate,dealstage,amount"
                )
                if after:
                    url += f"&after={after}"

                data = _hs_get(url, token)
                for d in data.get("results", []):
                    props = d.get("properties", {})
                    cd = (props.get("createdate") or "")[:10]
                    if cd and start_date.isoformat() <= cd <= end_date.isoformat():
                        day_metrics[cd]["deals_created"] += 1
                        fetched += 1

                    close = (props.get("closedate") or "")[:10]
                    stage = (props.get("dealstage") or "").lower()
                    if close and start_date.isoformat() <= close <= end_date.isoformat():
                        if "won" in stage or "closed" in stage:
                            day_metrics[close]["deals_closed_won"] += 1
                            day_metrics[close]["revenue"] += self._safe_float(
                                props.get("amount")
                            )

                paging = data.get("paging", {}).get("next", {})
                after = paging.get("after")
                if not after or fetched > 10000:
                    break
                time.sleep(self.RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"HubSpot deals fetch: {e}")

    def _pull_email_events(
        self, token: str, start_date: date, end_date: date,
        day_metrics: Dict[str, Dict[str, Any]],
    ) -> None:
        start_ms = int(datetime.combine(start_date, datetime.min.time(),
                                         tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime.combine(end_date + timedelta(days=1),
                                       datetime.min.time(),
                                       tzinfo=timezone.utc).timestamp() * 1000)
        for event_type in ("SENT", "OPEN", "CLICK"):
            offset = None
            fetched = 0
            try:
                while True:
                    url = (
                        f"{HUBSPOT_BASE}/email/public/v1/events"
                        f"?eventType={event_type}"
                        f"&startTimestamp={start_ms}&endTimestamp={end_ms}"
                        f"&limit=250"
                    )
                    if offset:
                        url += f"&offset={offset}"

                    data = _hs_get(url, token)
                    for ev in data.get("events", []):
                        ts = ev.get("created", 0)
                        if ts:
                            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                            key = {"SENT": "emails_sent", "OPEN": "emails_opened",
                                   "CLICK": "emails_clicked"}.get(event_type, "")
                            if key:
                                day_metrics[d][key] += 1
                                fetched += 1

                    if not data.get("hasMore"):
                        break
                    offset = data.get("offset")
                    if fetched > 50000:
                        break
                    time.sleep(self.RATE_LIMIT_DELAY)
            except Exception as e:
                logger.debug(f"HubSpot email events ({event_type}): {e}")
