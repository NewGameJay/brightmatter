"""Google Ads adapter using the google-ads Python SDK."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List

from .base import BasePlatformAdapter, DailyMetricRow, PlatformConfig

logger = logging.getLogger(__name__)

_CAMPAIGN_QUERY = """
SELECT
  segments.date,
  campaign.id,
  campaign.name,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign.status,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value,
  metrics.ctr,
  metrics.average_cpc,
  metrics.video_views,
  metrics.interactions
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND campaign.status != 'REMOVED'
ORDER BY segments.date
"""


class GoogleAdsAdapter(BasePlatformAdapter):
    PLATFORM = "google_ads"
    RATE_LIMIT_DELAY = 0.5
    MAX_LOOKBACK_DAYS = 1095

    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        try:
            from google.ads.googleads.client import GoogleAdsClient
        except ImportError:
            logger.warning("google-ads SDK not installed, using REST fallback")
            return self._pull_via_rest(config, start_date, end_date)

        creds = config.credentials
        customer_id = str(config.account_id).replace("-", "")

        client_config = {
            "developer_token": creds["developer_token"],
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "use_proto_plus": True,
        }
        login_cid = creds.get("login_customer_id", "")
        if login_cid:
            client_config["login_customer_id"] = str(login_cid).replace("-", "")

        try:
            gads_client = GoogleAdsClient.load_from_dict(client_config)
        except Exception as e:
            logger.error(f"GoogleAds client init failed for {config.client_name}: {e}")
            return []

        ga_service = gads_client.get_service("GoogleAdsService")

        # Chunk into 90-day windows to stay within API limits
        rows: List[DailyMetricRow] = []
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(chunk_start + timedelta(days=89), end_date)
            query = _CAMPAIGN_QUERY.format(
                start=chunk_start.isoformat(),
                end=chunk_end.isoformat(),
            )
            try:
                stream = ga_service.search_stream(
                    customer_id=customer_id,
                    query=query,
                )
                day_agg: Dict[str, Dict[str, Any]] = {}
                for batch in stream:
                    for row in batch.results:
                        d = row.segments.date  # YYYY-MM-DD string
                        if d not in day_agg:
                            day_agg[d] = {
                                "spend": 0.0,
                                "impressions": 0,
                                "clicks": 0,
                                "conversions": 0.0,
                                "conversion_value": 0.0,
                                "ctr": 0.0,
                                "avg_cpc": 0.0,
                                "campaigns": 0,
                                "video_views": 0,
                            }
                        m = day_agg[d]
                        cost = row.metrics.cost_micros / 1_000_000
                        m["spend"] += cost
                        m["impressions"] += row.metrics.impressions
                        m["clicks"] += row.metrics.clicks
                        m["conversions"] += row.metrics.conversions
                        m["conversion_value"] += row.metrics.conversions_value
                        m["video_views"] += row.metrics.video_views
                        m["campaigns"] += 1

                for d_str, m in sorted(day_agg.items()):
                    if m["spend"] > 0 and m["clicks"] > 0:
                        m["cpc"] = round(m["spend"] / m["clicks"], 4)
                    if m["impressions"] > 0:
                        m["ctr"] = round(m["clicks"] / m["impressions"], 6)
                    if m["spend"] > 0 and m["conversions"] > 0:
                        m["cpa"] = round(m["spend"] / m["conversions"], 2)
                        m["roas"] = round(m["conversion_value"] / m["spend"], 4)

                    rows.append(DailyMetricRow(
                        metric_date=date.fromisoformat(d_str),
                        metrics=m,
                        record_count=m["campaigns"],
                    ))

                time.sleep(self.RATE_LIMIT_DELAY)
            except Exception as e:
                logger.error(
                    f"GoogleAds query failed for {config.client_name} "
                    f"({chunk_start}–{chunk_end}): {e}"
                )

            chunk_start = chunk_end + timedelta(days=1)

        logger.info(
            f"GoogleAds: pulled {len(rows)} days for "
            f"{config.client_name} ({customer_id})"
        )
        return rows

    # ── REST fallback (no SDK) ──────────────────────────────────

    def _pull_via_rest(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        """Minimal REST-based Google Ads API fallback.

        Uses the google-ads REST endpoint directly with OAuth2 tokens.
        Less efficient than the SDK but works without the heavy dependency.
        """
        import json
        import urllib.request
        import urllib.error

        creds = config.credentials
        customer_id = str(config.account_id).replace("-", "")
        login_cid = str(creds.get("login_customer_id", customer_id)).replace("-", "")

        # Get an access token from the refresh token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = json.dumps({
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(
            token_url,
            data=token_data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            access_token = json.loads(resp.read())["access_token"]
        except Exception as e:
            logger.error(f"GoogleAds OAuth token refresh failed: {e}")
            return []

        api_url = (
            f"https://googleads.googleapis.com/v17/customers/"
            f"{customer_id}/googleAds:searchStream"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": creds["developer_token"],
            "Content-Type": "application/json",
        }
        if login_cid and login_cid != customer_id:
            headers["login-customer-id"] = login_cid

        rows: List[DailyMetricRow] = []
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(chunk_start + timedelta(days=89), end_date)
            query = _CAMPAIGN_QUERY.format(
                start=chunk_start.isoformat(),
                end=chunk_end.isoformat(),
            )
            body = json.dumps({"query": query}).encode()
            req = urllib.request.Request(api_url, data=body, headers=headers)

            try:
                resp = urllib.request.urlopen(req, timeout=120)
                results = json.loads(resp.read())
                day_agg: Dict[str, Dict[str, Any]] = {}

                for batch in results if isinstance(results, list) else [results]:
                    for r in batch.get("results", []):
                        d = r.get("segments", {}).get("date", "")
                        if not d:
                            continue
                        if d not in day_agg:
                            day_agg[d] = {
                                "spend": 0.0, "impressions": 0, "clicks": 0,
                                "conversions": 0.0, "conversion_value": 0.0,
                                "campaigns": 0, "video_views": 0,
                            }
                        m = day_agg[d]
                        metrics = r.get("metrics", {})
                        m["spend"] += self._safe_float(metrics.get("costMicros", 0)) / 1_000_000
                        m["impressions"] += self._safe_int(metrics.get("impressions", 0))
                        m["clicks"] += self._safe_int(metrics.get("clicks", 0))
                        m["conversions"] += self._safe_float(metrics.get("conversions", 0))
                        m["conversion_value"] += self._safe_float(metrics.get("conversionsValue", 0))
                        m["video_views"] += self._safe_int(metrics.get("videoViews", 0))
                        m["campaigns"] += 1

                for d_str, m in sorted(day_agg.items()):
                    if m["clicks"] > 0:
                        m["cpc"] = round(m["spend"] / m["clicks"], 4)
                    if m["impressions"] > 0:
                        m["ctr"] = round(m["clicks"] / m["impressions"], 6)
                    if m["conversions"] > 0:
                        m["cpa"] = round(m["spend"] / m["conversions"], 2)
                    if m["spend"] > 0 and m["conversion_value"] > 0:
                        m["roas"] = round(m["conversion_value"] / m["spend"], 4)
                    rows.append(DailyMetricRow(
                        metric_date=date.fromisoformat(d_str),
                        metrics=m,
                        record_count=m["campaigns"],
                    ))

                time.sleep(self.RATE_LIMIT_DELAY * 2)
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:300]
                logger.error(f"GoogleAds REST error {e.code}: {body}")
            except Exception as e:
                logger.error(f"GoogleAds REST failed: {e}")

            chunk_start = chunk_end + timedelta(days=1)

        logger.info(f"GoogleAds REST: {len(rows)} days for {config.client_name}")
        return rows
