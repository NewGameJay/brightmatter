"""Phase 2 change-detectors: rolling-period comparisons.

Each function here pairs with a Phase 1 state-detector in `detectors.py`.
The state-detector answers "what is true now?"; the change-detector
answers "how did the most recent equivalent window compare to the prior
equivalent window?"

Both kinds of signals can fire independently:
  - state-only:  stably bad (e.g. capped at 30% for the last 28 days)
  - change-only: trending bad (15% → 28%) or improving from bad (45% → 30%)
  - both:        moving at an already-bad level
  - neither:     stable and within bounds

The two run side-by-side; downstream consumers can filter by signal_type
to get just state or just change views.

Window anchoring: change-detectors anchor to MAX(date) FROM daily_metrics
rather than current_date. This keeps the rolling comparison fair when the
data is even one day stale (which happens routinely between ingest runs).
The systemic anchor question for ALL detectors is tracked separately.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from brightmatter.models.patterns import PatternDomain, Severity, Signal
from brightmatter.storage.database import Database
from brightmatter.thresholds import effective_thresholds


def _now():
    return datetime.now(timezone.utc)


def _id():
    return uuid.uuid4().hex[:12]


def _data_anchor_date(db: Database) -> str | None:
    """Return MAX(date) from daily_metrics as an ISO string, or None if empty.

    Change-detectors anchor windows to this date instead of current_date so
    rolling comparisons stay fair when ingestion lags behind real-world today.
    """
    row = db.fetchone("SELECT max(date) FROM daily_metrics")
    if not row or row[0] is None:
        return None
    return row[0].isoformat()


def windowed(sql: str, anchor: str) -> str:
    """Rebind ``current_date`` in detector SQL to the data anchor date.

    Substitutes the literal token ``current_date`` with ``DATE 'anchor'`` so
    every ``date >= current_date - N`` window lands on the ingested data range
    rather than real-world today. Without this, state-detectors silently emit
    zero signals whenever the data is staler than their shortest window (which
    happens routinely between ingest runs). Safe for plain strings,
    pre-evaluated f-strings, and ``?``-parameterized queries — it touches only
    the keyword. Callers must guard ``anchor is None`` (empty table) first.
    """
    return sql.replace("current_date", f"DATE '{anchor}'")


def detect_budget_capped_change(db: Database) -> list[Signal]:
    """Week-over-week delta in avg(search_budget_lost_is) at the campaign level.

    Thresholds: config/thresholds.yaml → budget_capped_change.
    """
    th = effective_thresholds("budget_capped_change")
    window = int(th["window_days"])
    min_delta = float(th["min_delta_pp"])
    min_days = int(th["min_days_with_data"])

    anchor = _data_anchor_date(db)
    if anchor is None:
        return []

    rows = db.fetchall(f"""
        WITH cur AS (
            SELECT account_id, campaign_id, campaign_name,
                   avg(search_budget_lost_is) as cur_avg,
                   count(*) as cur_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {window}
              AND date <= DATE '{anchor}'
              AND search_budget_lost_is IS NOT NULL
            GROUP BY account_id, campaign_id, campaign_name
            HAVING count(*) >= {min_days}
        ),
        prior AS (
            SELECT account_id, campaign_id,
                   avg(search_budget_lost_is) as prior_avg,
                   count(*) as prior_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {2 * window}
              AND date <= DATE '{anchor}' - {window}
              AND search_budget_lost_is IS NOT NULL
            GROUP BY account_id, campaign_id
            HAVING count(*) >= {min_days}
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.cur_avg, p.prior_avg,
               c.cur_avg - p.prior_avg as delta,
               c.cur_days, p.prior_days
        FROM cur c
        JOIN prior p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE ABS(c.cur_avg - p.prior_avg) >= {min_delta}
        ORDER BY ABS(c.cur_avg - p.prior_avg) DESC
    """)

    signals: list[Signal] = []
    for r in rows:
        acct, camp_id, camp_name, cur_avg, prior_avg, delta, cur_days, prior_days = r
        direction = "worsening" if delta > 0 else "improving"
        sign = "+" if delta > 0 else ""
        signals.append(Signal(
            signal_id=_id(),
            account_id=acct,
            campaign_id=camp_id,
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="budget_capped_change",
            severity=Severity.INFO,
            value=cur_avg,
            threshold=prior_avg,
            message=(
                f"Campaign '{camp_name}' budget pressure {direction}: "
                f"{prior_avg:.0%} → {cur_avg:.0%} IS lost to budget "
                f"({sign}{delta * 100:.0f}pp WoW)"
            ),
            data={
                "campaign_id": camp_id,
                "current_avg_budget_lost_is": cur_avg,
                "prior_avg_budget_lost_is": prior_avg,
                "delta_pp": delta,
                "direction": direction,
                "current_days_with_data": cur_days,
                "prior_days_with_data": prior_days,
                "window_days": window,
                "anchor_date": anchor,
            },
            detected_at=_now(),
        ))
    return signals


def detect_budget_limited_is_change(db: Database) -> list[Signal]:
    """Week-over-week delta in avg(search_budget_lost_is) at the campaign level,
    over a 7-day window (parent: budget_limited_is).

    Thresholds: config/thresholds.yaml → budget_limited_is_change.
    """
    th = effective_thresholds("budget_limited_is_change")
    window = int(th["window_days"])
    min_delta = float(th["min_delta_pp"])
    min_days = int(th["min_days_with_data"])
    min_cost = int(th["min_cost_micros"])

    anchor = _data_anchor_date(db)
    if anchor is None:
        return []

    rows = db.fetchall(f"""
        WITH cur AS (
            SELECT account_id, campaign_id, campaign_name,
                   avg(search_budget_lost_is) as cur_avg,
                   count(*) as cur_days,
                   sum(cost_micros) as cur_cost
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {window}
              AND date <= DATE '{anchor}'
              AND search_budget_lost_is IS NOT NULL
            GROUP BY account_id, campaign_id, campaign_name
            HAVING count(*) >= {min_days}
               AND sum(cost_micros) >= {min_cost}
        ),
        prior AS (
            SELECT account_id, campaign_id,
                   avg(search_budget_lost_is) as prior_avg,
                   count(*) as prior_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {2 * window}
              AND date <= DATE '{anchor}' - {window}
              AND search_budget_lost_is IS NOT NULL
            GROUP BY account_id, campaign_id
            HAVING count(*) >= {min_days}
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.cur_avg, p.prior_avg,
               c.cur_avg - p.prior_avg as delta,
               c.cur_days, p.prior_days, c.cur_cost
        FROM cur c
        JOIN prior p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE ABS(c.cur_avg - p.prior_avg) >= {min_delta}
        ORDER BY ABS(c.cur_avg - p.prior_avg) DESC
    """)

    signals: list[Signal] = []
    for r in rows:
        acct, camp_id, camp_name, cur_avg, prior_avg, delta, cur_days, prior_days, cur_cost = r
        direction = "worsening" if delta > 0 else "improving"
        sign = "+" if delta > 0 else ""
        signals.append(Signal(
            signal_id=_id(),
            account_id=acct,
            campaign_id=camp_id,
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="budget_limited_is_change",
            severity=Severity.INFO,
            value=cur_avg,
            threshold=prior_avg,
            message=(
                f"Campaign '{camp_name}' budget pressure {direction}: "
                f"{prior_avg:.0%} → {cur_avg:.0%} IS lost to budget "
                f"({sign}{delta * 100:.0f}pp WoW)"
            ),
            data={
                "campaign_id": camp_id,
                "current_avg_budget_lost_is": cur_avg,
                "prior_avg_budget_lost_is": prior_avg,
                "delta_pp": delta,
                "direction": direction,
                "current_days_with_data": cur_days,
                "prior_days_with_data": prior_days,
                "current_cost_micros": cur_cost,
                "window_days": window,
                "anchor_date": anchor,
            },
            detected_at=_now(),
        ))
    return signals


def detect_pmax_low_conv_volume_change(db: Database) -> list[Signal]:
    """Rolling-period delta in PMax conversion count (parent: pmax_low_conv_volume).

    Compares current 14d sum(conversions) against prior 14d for ENABLED
    PERFORMANCE_MAX campaigns. Fires on relative change ≥25% AND absolute
    change ≥5 conversions, in either direction. Cost floor mirrors the
    parent's $1k/30d, scaled to $500/14d, to suppress firing on dead or
    test campaigns.

    Thresholds: config/thresholds.yaml → pmax_low_conv_volume_change.
    """
    th = effective_thresholds("pmax_low_conv_volume_change")
    window = int(th["window_days"])
    min_pct = float(th["min_pct_delta"])
    min_abs = float(th["min_abs_delta"])
    min_days = int(th["min_days_with_data"])
    min_cost = int(th["min_cost_micros"])

    anchor = _data_anchor_date(db)
    if anchor is None:
        return []

    rows = db.fetchall(f"""
        WITH cur AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(conversions) as cur_conv,
                   sum(cost_micros) as cur_cost,
                   count(*) as cur_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {window}
              AND date <= DATE '{anchor}'
              AND campaign_type = 'PERFORMANCE_MAX'
              AND status = 'ENABLED'
            GROUP BY account_id, campaign_id, campaign_name
            HAVING count(*) >= {min_days}
               AND sum(cost_micros) >= {min_cost}
        ),
        prior AS (
            SELECT account_id, campaign_id,
                   sum(conversions) as prior_conv,
                   count(*) as prior_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {2 * window}
              AND date <= DATE '{anchor}' - {window}
              AND campaign_type = 'PERFORMANCE_MAX'
              AND status = 'ENABLED'
            GROUP BY account_id, campaign_id
            HAVING count(*) >= {min_days}
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.cur_conv, p.prior_conv,
               c.cur_conv - p.prior_conv as abs_delta,
               c.cur_days, p.prior_days, c.cur_cost
        FROM cur c
        JOIN prior p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE p.prior_conv > 0
          AND ABS(c.cur_conv - p.prior_conv) >= {min_abs}
          AND ABS(c.cur_conv - p.prior_conv) / p.prior_conv >= {min_pct}
        ORDER BY ABS(c.cur_conv - p.prior_conv) / NULLIF(p.prior_conv, 0) DESC
    """)

    signals: list[Signal] = []
    for r in rows:
        acct, camp_id, camp_name, cur_conv, prior_conv, abs_delta, cur_days, prior_days, cur_cost = r
        pct_delta = abs_delta / prior_conv if prior_conv else 0.0
        direction = "improving" if abs_delta > 0 else "worsening"
        sign = "+" if abs_delta > 0 else ""
        signals.append(Signal(
            signal_id=_id(),
            account_id=acct,
            campaign_id=camp_id,
            domain=PatternDomain.PERFORMANCE_MAX,
            signal_type="pmax_low_conv_volume_change",
            severity=Severity.INFO,
            value=cur_conv,
            threshold=prior_conv,
            message=(
                f"PMax '{camp_name}' conversion volume {direction}: "
                f"{prior_conv:.0f} → {cur_conv:.0f} conv "
                f"({sign}{pct_delta * 100:.0f}% over {window}d)"
            ),
            data={
                "campaign_id": camp_id,
                "current_conversions": cur_conv,
                "prior_conversions": prior_conv,
                "abs_delta": abs_delta,
                "pct_delta": pct_delta,
                "direction": direction,
                "current_days_with_data": cur_days,
                "prior_days_with_data": prior_days,
                "current_cost_micros": cur_cost,
                "window_days": window,
                "anchor_date": anchor,
            },
            detected_at=_now(),
        ))
    return signals


def detect_cvr_change(db: Database) -> list[Signal]:
    """Bidirectional rolling-period delta in CVR (parent: cvr_drop).

    Same 7d-vs-7d windows as cvr_drop, but fires on movement in either
    direction at a smaller delta (15% relative). Independent from cvr_drop:
    a 35% drop fires both (state-level "investigate" + change-level
    "movement"); a 20% drop fires only this; a 25% improvement fires only
    this. Both kinds of signals can coexist for the same campaign.

    Thresholds: config/thresholds.yaml → cvr_change.
    """
    th = effective_thresholds("cvr_change")
    window = int(th["window_days"])
    min_pct = float(th["min_pct_delta"])
    min_prior_clicks = int(th["min_prior_clicks"])
    min_current_clicks = int(th["min_current_clicks"])
    min_prior_conv = float(th["min_prior_conv"])
    min_prior_cvr = float(th["min_prior_cvr"])

    anchor = _data_anchor_date(db)
    if anchor is None:
        return []

    rows = db.fetchall(f"""
        WITH cur AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(conversions) as cur_conv,
                   sum(clicks) as cur_clicks
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {window}
              AND date <= DATE '{anchor}'
            GROUP BY account_id, campaign_id, campaign_name
            HAVING sum(clicks) >= {min_current_clicks}
        ),
        prior AS (
            SELECT account_id, campaign_id,
                   sum(conversions) as prior_conv,
                   sum(clicks) as prior_clicks
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {2 * window}
              AND date <= DATE '{anchor}' - {window}
            GROUP BY account_id, campaign_id
            HAVING sum(clicks) >= {min_prior_clicks}
               AND sum(conversions) >= {min_prior_conv}
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.cur_conv / NULLIF(c.cur_clicks, 0) as cur_cvr,
               p.prior_conv / NULLIF(p.prior_clicks, 0) as prior_cvr,
               c.cur_clicks, p.prior_clicks, c.cur_conv, p.prior_conv
        FROM cur c
        JOIN prior p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE p.prior_conv / NULLIF(p.prior_clicks, 0) >= {min_prior_cvr}
          AND ABS(
              (c.cur_conv / NULLIF(c.cur_clicks, 0)) -
              (p.prior_conv / NULLIF(p.prior_clicks, 0))
          ) / NULLIF(p.prior_conv / NULLIF(p.prior_clicks, 0), 0) >= {min_pct}
        ORDER BY
          ABS(
              (c.cur_conv / NULLIF(c.cur_clicks, 0)) -
              (p.prior_conv / NULLIF(p.prior_clicks, 0))
          ) / NULLIF(p.prior_conv / NULLIF(p.prior_clicks, 0), 0) DESC
    """)

    signals: list[Signal] = []
    for r in rows:
        acct, camp_id, camp_name, cur_cvr, prior_cvr, cur_clicks, prior_clicks, cur_conv, prior_conv = r
        delta = cur_cvr - prior_cvr
        pct_delta = delta / prior_cvr if prior_cvr else 0.0
        direction = "improving" if delta > 0 else "worsening"
        sign = "+" if delta > 0 else ""
        signals.append(Signal(
            signal_id=_id(),
            account_id=acct,
            campaign_id=camp_id,
            domain=PatternDomain.LANDING_PAGE,
            signal_type="cvr_change",
            severity=Severity.INFO,
            value=cur_cvr,
            threshold=prior_cvr,
            message=(
                f"Campaign '{camp_name}' CVR {direction}: "
                f"{prior_cvr:.1%} → {cur_cvr:.1%} "
                f"({sign}{pct_delta * 100:.0f}% WoW)"
            ),
            data={
                "campaign_id": camp_id,
                "current_cvr": cur_cvr,
                "prior_cvr": prior_cvr,
                "pct_delta": pct_delta,
                "direction": direction,
                "current_clicks": cur_clicks,
                "prior_clicks": prior_clicks,
                "current_conversions": cur_conv,
                "prior_conversions": prior_conv,
                "window_days": window,
                "anchor_date": anchor,
            },
            detected_at=_now(),
        ))
    return signals


def detect_cpa_change(db: Database) -> list[Signal]:
    """Bidirectional rolling-period delta in CPA (parent: cpa_spike).

    Note: cpa_spike compares 7d recent against an UNEQUAL 8-30d baseline
    at a 3x multiplier (a different shape than other change-detectors).
    cpa_change uses EQUAL 7d-vs-7d windows at a ~25% bidirectional delta —
    a slower, symmetric "is CPA drifting" view that pairs with cpa_spike's
    "did CPA spike vs its normal baseline" view. Both can fire together
    (sharp spike) or separately (gradual drift vs sudden spike).

    Thresholds: config/thresholds.yaml → cpa_change.
    """
    th = effective_thresholds("cpa_change")
    window = int(th["window_days"])
    min_pct = float(th["min_pct_delta"])
    min_conv = float(th["min_conv_per_window"])
    min_active_days = int(th["min_active_days"])
    max_single_day_share = float(th["max_single_day_share"])

    anchor = _data_anchor_date(db)
    if anchor is None:
        return []

    rows = db.fetchall(f"""
        WITH cur AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(cost_micros) as cur_cost,
                   sum(conversions) as cur_conv,
                   count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) as cur_active_days,
                   max(cost_micros) / NULLIF(sum(cost_micros), 0) as cur_max_day_share
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {window}
              AND date <= DATE '{anchor}'
            GROUP BY account_id, campaign_id, campaign_name
            HAVING sum(conversions) >= {min_conv}
               AND count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) >= {min_active_days}
               AND max(cost_micros) / NULLIF(sum(cost_micros), 0) <= {max_single_day_share}
        ),
        prior AS (
            SELECT account_id, campaign_id,
                   sum(cost_micros) as prior_cost,
                   sum(conversions) as prior_conv,
                   count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) as prior_active_days
            FROM daily_metrics
            WHERE date > DATE '{anchor}' - {2 * window}
              AND date <= DATE '{anchor}' - {window}
            GROUP BY account_id, campaign_id
            HAVING sum(conversions) >= {min_conv}
               AND count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) >= {min_active_days}
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.cur_cost / NULLIF(c.cur_conv, 0) / 1000000.0 as cur_cpa,
               p.prior_cost / NULLIF(p.prior_conv, 0) / 1000000.0 as prior_cpa,
               c.cur_conv, p.prior_conv,
               c.cur_active_days, p.prior_active_days,
               c.cur_max_day_share
        FROM cur c
        JOIN prior p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE p.prior_cost > 0 AND c.cur_cost > 0
          AND ABS(
              (c.cur_cost / NULLIF(c.cur_conv, 0)) -
              (p.prior_cost / NULLIF(p.prior_conv, 0))
          ) / NULLIF(p.prior_cost / NULLIF(p.prior_conv, 0), 0) >= {min_pct}
        ORDER BY
          ABS(
              (c.cur_cost / NULLIF(c.cur_conv, 0)) -
              (p.prior_cost / NULLIF(p.prior_conv, 0))
          ) / NULLIF(p.prior_cost / NULLIF(p.prior_conv, 0), 0) DESC
    """)

    signals: list[Signal] = []
    for r in rows:
        acct, camp_id, camp_name, cur_cpa, prior_cpa, cur_conv, prior_conv, cur_active, prior_active, cur_max_share = r
        delta = cur_cpa - prior_cpa
        pct_delta = delta / prior_cpa if prior_cpa else 0.0
        # Note: CPA goes UP = worsening, DOWN = improving (opposite of CVR).
        direction = "worsening" if delta > 0 else "improving"
        sign = "+" if delta > 0 else ""
        signals.append(Signal(
            signal_id=_id(),
            account_id=acct,
            campaign_id=camp_id,
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="cpa_change",
            severity=Severity.INFO,
            value=cur_cpa,
            threshold=prior_cpa,
            message=(
                f"Campaign '{camp_name}' CPA {direction}: "
                f"${prior_cpa:.2f} → ${cur_cpa:.2f} "
                f"({sign}{pct_delta * 100:.0f}% WoW)"
            ),
            data={
                "campaign_id": camp_id,
                "current_cpa": cur_cpa,
                "prior_cpa": prior_cpa,
                "pct_delta": pct_delta,
                "direction": direction,
                "current_conversions": cur_conv,
                "prior_conversions": prior_conv,
                "current_active_days": cur_active,
                "prior_active_days": prior_active,
                "current_max_day_share": cur_max_share,
                "window_days": window,
                "anchor_date": anchor,
            },
            detected_at=_now(),
        ))
    return signals


def run_all_change_detectors(db: Database) -> list[Signal]:
    """Run every change-detector and return all signals found.

    Add new change-detectors here as they're written. The state-detector
    counterparts live in detectors.py.
    """
    signals: list[Signal] = []
    signals.extend(detect_budget_capped_change(db))
    signals.extend(detect_budget_limited_is_change(db))
    signals.extend(detect_pmax_low_conv_volume_change(db))
    signals.extend(detect_cvr_change(db))
    signals.extend(detect_cpa_change(db))
    return signals
