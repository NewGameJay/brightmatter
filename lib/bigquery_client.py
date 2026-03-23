"""
BrightMatter BigQuery Client

Thin wrapper around google.cloud.bigquery for reading historical
ad spend, campaign performance, and LTV/ROAS data from the
MH-OS warehouse (marketerhire-warehouse).

Credentials (checked in order):
    BIGQUERY_CREDENTIALS_JSON  — inline JSON string (same as MH-OS Trigger.dev)
    GOOGLE_APPLICATION_CREDENTIALS — path to service account JSON file

Usage:
    from lib.bigquery_client import get_bq_client
    bq = get_bq_client()
    rows = bq.query_daily_spend("2024-01-01", "2026-03-20")
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BQ_PROJECT = "marketerhire-warehouse"

_client = None
_lock = threading.Lock()


def get_bq_client() -> "BigQueryClient":
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        _client = BigQueryClient()
        return _client


class BigQueryClient:
    """Read-only BigQuery client for MH-OS warehouse data."""

    def __init__(self):
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ImportError(
                "google-cloud-bigquery required. "
                "Install with: pip install google-cloud-bigquery"
            )

        creds_json = os.environ.get("BIGQUERY_CREDENTIALS_JSON", "")
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

        if creds_json:
            creds_dict = json.loads(creds_json)
            project = creds_dict.get("project_id", BQ_PROJECT)

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(creds_dict, tmp)
            tmp.close()
            self._client = bigquery.Client.from_service_account_json(
                tmp.name, project=project
            )
            logger.info(f"BigQuery client initialized from JSON env (project={project})")
        elif creds_path:
            self._client = bigquery.Client.from_service_account_json(
                creds_path, project=BQ_PROJECT
            )
            logger.info(f"BigQuery client initialized from file (project={BQ_PROJECT})")
        else:
            raise ValueError(
                "BIGQUERY_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS "
                "must be set for BigQuery access."
            )

    def _query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL and return rows as list of dicts."""
        result = self._client.query(sql).result()
        return [dict(row) for row in result]

    def query_daily_spend(
        self,
        start_date: str,
        end_date: str,
        channel: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query reporting.fact_daily_spend for channel-level daily data.

        Columns: dt, channel, region, spend, nbr_ff, nbr_mql, nbr_sql,
        nbr_appt, nbr_qtb, nbr_cs, cs_deal_value, qtb_deal_value.
        """
        channel_filter = f"AND channel = '{channel}'" if channel else ""
        sql = f"""
        SELECT
            dt,
            channel,
            COALESCE(spend, 0) AS spend,
            COALESCE(nbr_ff, 0) AS nbr_ff,
            COALESCE(nbr_mql, 0) AS nbr_mql,
            COALESCE(nbr_sql, 0) AS nbr_sql,
            COALESCE(nbr_appt, 0) AS nbr_appt,
            COALESCE(nbr_qtb, 0) AS nbr_qtb,
            COALESCE(nbr_cs, 0) AS nbr_cs,
            COALESCE(cs_deal_value, 0) AS cs_deal_value
        FROM `{BQ_PROJECT}.reporting.fact_daily_spend`
        WHERE dt BETWEEN '{start_date}' AND '{end_date}'
          {channel_filter}
        ORDER BY dt, channel
        """
        return self._query(sql)

    def query_campaign_spend(
        self,
        start_date: str,
        end_date: str,
        channel: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query reporting.fact_daily_spend__by_campaign for campaign-level data."""
        channel_filter = f"AND channel = '{channel}'" if channel else ""
        sql = f"""
        SELECT
            dt,
            channel,
            campaign,
            COALESCE(spend, 0) AS spend,
            COALESCE(clicks, 0) AS clicks,
            COALESCE(impressions, 0) AS impressions,
            COALESCE(nbr_ff, 0) AS nbr_ff,
            COALESCE(nbr_appt_sch, 0) AS nbr_appt_sch,
            COALESCE(nbr_cs, 0) AS nbr_cs,
            COALESCE(total_net_rev, 0) AS total_net_rev
        FROM `{BQ_PROJECT}.reporting.fact_daily_spend__by_campaign`
        WHERE dt BETWEEN '{start_date}' AND '{end_date}'
          {channel_filter}
        ORDER BY dt, channel, campaign
        """
        return self._query(sql)

    def query_ltv_roas(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Query reporting.fact_daily_spend_hdyhau for LTV/ROAS metrics."""
        sql = f"""
        SELECT
            dt,
            channel,
            COALESCE(spend, 0) AS spend,
            COALESCE(nbr_customer, 0) AS nbr_customer,
            COALESCE(ltv_unbounded, 0) AS ltv_unbounded,
            COALESCE(ltv_3mo, 0) AS ltv_3mo,
            COALESCE(ltv_12mo, 0) AS ltv_12mo,
            SAFE_DIVIDE(SUM(ltv_unbounded), NULLIF(SUM(spend), 0)) AS roas_ltv,
            SAFE_DIVIDE(SUM(spend), NULLIF(SUM(nbr_customer), 0)) AS cac
        FROM `{BQ_PROJECT}.reporting.fact_daily_spend_hdyhau`
        WHERE dt BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY dt, channel, spend, nbr_customer, ltv_unbounded, ltv_3mo, ltv_12mo
        ORDER BY dt, channel
        """
        return self._query(sql)

    def query_weekly_channel_summary(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Aggregate daily spend into weekly channel summaries with computed CPA."""
        sql = f"""
        SELECT
            DATE_TRUNC(dt, WEEK(MONDAY)) AS week_start,
            channel,
            SUM(spend) AS total_spend,
            SUM(nbr_ff) AS total_ff,
            SUM(nbr_appt) AS total_appt,
            SUM(nbr_cs) AS total_cs,
            SUM(cs_deal_value) AS total_deal_value,
            SAFE_DIVIDE(SUM(spend), NULLIF(SUM(nbr_appt), 0)) AS cpa,
            SAFE_DIVIDE(SUM(spend), NULLIF(SUM(nbr_cs), 0)) AS cac
        FROM `{BQ_PROJECT}.reporting.fact_daily_spend`
        WHERE dt BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY week_start, channel
        ORDER BY week_start, channel
        """
        return self._query(sql)
