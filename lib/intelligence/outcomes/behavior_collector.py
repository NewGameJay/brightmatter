"""
MH1 User Behavior Signal Collector

Queries PostHog (via the Query API) and Firebase user_activity for
behavioral signals that feed the composite outcome scorer.

Signals collected:
    - time_to_approval: hours from first view to plan/report approval
    - edit_depth: ratio of content edited (0-1, heavy editing = poor fit)
    - report_views: view count for the report
    - scroll_depth_pct: max scroll depth percentage
    - shared: whether the report was shared externally
    - adopted: whether the client implemented recommendations
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BehaviorCollector:
    """
    Collects user behavior signals from PostHog and Firebase for a
    given report/module within a time window.
    """

    def __init__(
        self,
        firebase_client: Any = None,
        posthog_api_key: Optional[str] = None,
        posthog_project_id: Optional[str] = None,
        posthog_host: str = "https://app.posthog.com",
    ):
        self._firebase = firebase_client
        self._posthog_api_key = posthog_api_key or os.environ.get("POSTHOG_API_KEY")
        self._posthog_project_id = posthog_project_id or os.environ.get("POSTHOG_PROJECT_ID")
        self._posthog_host = posthog_host

    def collect(
        self,
        client_id: str,
        module_id: str,
        report_id: Optional[str] = None,
        window_start: Optional[str] = None,
        window_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Collect all behavior signals for a client/module within a window.

        Returns a dict suitable for CompositeSignalComputer._score_behavior().
        """
        signals: Dict[str, Any] = {}

        firebase_signals = self._collect_firebase(
            client_id, module_id, report_id, window_start, window_end
        )
        signals.update(firebase_signals)

        posthog_signals = self._collect_posthog(
            client_id, module_id, report_id, window_start, window_end
        )
        signals.update(posthog_signals)

        return signals

    def _collect_firebase(
        self,
        client_id: str,
        module_id: str,
        report_id: Optional[str],
        window_start: Optional[str],
        window_end: Optional[str],
    ) -> Dict[str, Any]:
        """Read user_activity and feedback from Firebase."""
        signals: Dict[str, Any] = {}
        if not self._firebase:
            return signals

        try:
            activities = self._firebase.query(
                "user_activity",
                filters=[("client_id", "==", client_id)],
                limit=100,
            )

            if not activities:
                return signals

            first_view_ts = None
            approval_ts = None
            view_count = 0
            shared = False
            adopted = False

            for act in activities:
                doc = act if isinstance(act, dict) else (
                    act.to_dict() if hasattr(act, "to_dict") else {}
                )
                action = doc.get("action", "")
                ts = doc.get("timestamp", "")
                meta = doc.get("metadata", {})
                act_module = meta.get("module_id", "") or doc.get("module_id", "")

                if act_module and act_module != module_id:
                    continue

                if window_start and ts and ts < window_start:
                    continue
                if window_end and ts and ts > window_end:
                    continue

                if action == "viewed_report":
                    view_count += 1
                    if first_view_ts is None or ts < first_view_ts:
                        first_view_ts = ts
                elif action in ("approved_report", "approved_plan"):
                    if approval_ts is None or ts < approval_ts:
                        approval_ts = ts
                elif action == "deployed_report":
                    adopted = True
                elif action == "shared_report":
                    shared = True

            if first_view_ts and approval_ts:
                try:
                    t0 = datetime.fromisoformat(first_view_ts.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(approval_ts.replace("Z", "+00:00"))
                    signals["time_to_approval_hours"] = max(
                        0.0, (t1 - t0).total_seconds() / 3600
                    )
                except (ValueError, TypeError):
                    pass

            signals["report_views"] = view_count
            signals["shared"] = shared
            signals["adopted"] = adopted

            # Check for feedback/rating
            if report_id:
                try:
                    feedback_doc = self._firebase.get_document(
                        f"clients/{client_id}/feedback", report_id
                    )
                    if feedback_doc:
                        signals["_feedback_rating"] = feedback_doc.get("rating")
                        signals["_feedback_comment"] = feedback_doc.get("comment")
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Firebase activity collection failed: {e}")

        return signals

    def _collect_posthog(
        self,
        client_id: str,
        module_id: str,
        report_id: Optional[str],
        window_start: Optional[str],
        window_end: Optional[str],
    ) -> Dict[str, Any]:
        """Query PostHog for event-level signals."""
        signals: Dict[str, Any] = {}

        if not self._posthog_api_key or not self._posthog_project_id:
            return signals

        try:
            import requests
        except ImportError:
            logger.debug("requests not available for PostHog queries")
            return signals

        try:
            end = window_end or datetime.now(timezone.utc).isoformat()
            start = window_start or (
                datetime.now(timezone.utc) - timedelta(days=8)
            ).isoformat()

            # HogQL query for report-level events
            filter_parts = [f"properties.client_id = '{client_id}'"]
            if report_id:
                filter_parts.append(f"properties.report_id = '{report_id}'")

            hogql = (
                f"SELECT event, count() as cnt, "
                f"max(toFloat64OrNull(properties.scroll_depth_pct)) as max_scroll, "
                f"sum(toFloat64OrNull(properties.char_diff)) as total_char_diff, "
                f"sum(toFloat64OrNull(properties.edit_count_in_session)) as total_edits "
                f"FROM events "
                f"WHERE {' AND '.join(filter_parts)} "
                f"AND timestamp >= '{start}' AND timestamp <= '{end}' "
                f"AND event IN ('REPORT_SCROLL_DEPTH', 'CONTENT_EDITED', "
                f"'REPORT_SHARED', 'REPORT_TIME_SPENT', 'PLAN_APPROVED') "
                f"GROUP BY event"
            )

            resp = requests.post(
                f"{self._posthog_host}/api/projects/{self._posthog_project_id}/query",
                headers={
                    "Authorization": f"Bearer {self._posthog_api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": {"kind": "HogQLQuery", "query": hogql}},
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                for row in data.get("results", []):
                    event_name = row[0] if len(row) > 0 else ""
                    count = row[1] if len(row) > 1 else 0

                    if event_name == "REPORT_SCROLL_DEPTH":
                        max_scroll = row[2] if len(row) > 2 else None
                        if max_scroll is not None:
                            signals["scroll_depth_pct"] = float(max_scroll)

                    elif event_name == "CONTENT_EDITED":
                        total_diff = row[3] if len(row) > 3 else 0
                        total_edits = row[4] if len(row) > 4 else 0
                        if total_diff and total_edits:
                            edit_ratio = min(1.0, float(total_diff) / 5000.0)
                            signals["edit_depth"] = edit_ratio

                    elif event_name == "REPORT_SHARED":
                        if count and int(count) > 0:
                            signals["shared"] = True

            else:
                logger.debug(
                    f"PostHog query returned {resp.status_code}: {resp.text[:200]}"
                )

        except Exception as e:
            logger.debug(f"PostHog behavior collection failed: {e}")

        return signals


__all__ = ["BehaviorCollector"]
