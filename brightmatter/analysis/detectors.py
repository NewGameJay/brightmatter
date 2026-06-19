"""Layer 1: Deterministic detectors — research-informed threshold rules.

Each detector produces Signal objects when a threshold is violated.
Thresholds are sourced from research/patterns/pattern-detection-logic.md
and research/experts/tier1-expert-frameworks.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from brightmatter.analysis.change_detectors import (
    _data_anchor_date,
    run_all_change_detectors,
    windowed,
)
from brightmatter.analysis.confidence import annotate as annotate_confidence
from brightmatter.analysis.naming import split_fractions
from brightmatter import benchmarks as _bench
from brightmatter.models.patterns import PatternDomain, Severity, Signal
from brightmatter.storage.database import Database
from brightmatter.thresholds import accounts_to_skip_for, effective_thresholds


def _now():
    return datetime.now(timezone.utc)


def _id():
    return uuid.uuid4().hex[:12]


def run_all_detectors(db: Database) -> list[Signal]:
    """Run every deterministic detector and return all signals found."""
    signals: list[Signal] = []
    signals.extend(detect_tracking_breaks(db))
    signals.extend(detect_low_quality_scores(db))
    signals.extend(detect_cpa_spikes(db))
    signals.extend(detect_impression_share_loss(db))
    signals.extend(detect_cvr_anomalies(db))
    signals.extend(detect_brand_nonbrand_contamination(db))
    signals.extend(detect_pmax_channel_imbalance(db))
    signals.extend(detect_auto_applied_changes(db))
    signals.extend(detect_budget_capped_campaigns(db))
    signals.extend(detect_bidding_antipatterns(db))
    # Wave 1
    signals.extend(detect_suspicious_primary_conversions(db))
    signals.extend(detect_duplicate_primary_conversions(db))
    signals.extend(detect_missing_conversion_value(db))
    signals.extend(detect_over_segmentation(db))
    # Wave 2
    signals.extend(detect_missing_brand_separation(db))
    signals.extend(detect_campaign_type_gaps(db))
    signals.extend(detect_broad_without_smart_bidding(db))
    signals.extend(detect_low_negative_ratio(db))
    # Wave 3
    signals.extend(detect_missing_extensions(db))
    signals.extend(detect_cross_account_outlier(db))
    signals.extend(detect_pmax_low_conversion_volume(db))
    signals.extend(detect_pmax_conversion_inflation(db))
    signals.extend(detect_search_terms_waste(db))
    signals.extend(detect_vertical_cpa_benchmark(db))

    # Phase 2 change-detectors: rolling-period comparisons that pair with
    # the Phase 1 state-detectors above. Both kinds of signals can fire
    # independently — see brightmatter/analysis/change_detectors.py.
    signals.extend(run_all_change_detectors(db))

    # Apply YAML-configured skip overrides. Each signal's `signal_type` is the
    # detector key in thresholds.yaml. If a detector has an override matching
    # the signal's account that sets `skip: true`, drop that signal here.
    # Detectors without a YAML entry (e.g. legacy ones not yet externalized)
    # are passed through unchanged.
    out = _apply_skip_overrides(db, signals)
    # Confidence framework: annotate every surviving signal with its tier and
    # the what-we-know / can't-rule-out / check-next frame (roadmap 1.5).
    for s in out:
        annotate_confidence(s)
    return out


def _apply_skip_overrides(db: Database, signals: list[Signal]) -> list[Signal]:
    skip_cache: dict[str, set[str]] = {}
    out: list[Signal] = []
    for s in signals:
        key = s.signal_type
        if key not in skip_cache:
            try:
                skip_cache[key] = accounts_to_skip_for(db, key)
            except KeyError:
                skip_cache[key] = set()  # detector has no YAML entry yet
        if s.account_id not in skip_cache[key]:
            out.append(s)
    return out


# ── Detector: Tracking Breaks ──
# Research: Causal Chain #1 — conversions drop >80% across ALL campaigns same day

def detect_tracking_breaks(db: Database) -> list[Signal]:
    """Detect accounts where conversions dropped >80% overnight across all campaigns."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed("""
        WITH daily AS (
            SELECT account_id, date,
                   sum(conversions) as total_conv,
                   sum(clicks) as total_clicks
            FROM daily_metrics
            WHERE date >= current_date - 14
            GROUP BY account_id, date
        ),
        comparison AS (
            SELECT a.account_id,
                   a.date as drop_date,
                   a.total_conv as current_conv,
                   b.total_conv as prior_conv,
                   a.total_clicks as current_clicks,
                   b.total_clicks as prior_clicks
            FROM daily a
            JOIN daily b ON a.account_id = b.account_id AND a.date = b.date + 1
            WHERE b.total_conv > 5
        )
        SELECT * FROM comparison
        WHERE current_conv < prior_conv * 0.2
          AND current_clicks > prior_clicks * 0.7
    """, anchor))
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], domain=PatternDomain.LANDING_PAGE,
            signal_type="tracking_break", severity=Severity.CRITICAL,
            value=r[3], threshold=r[4] * 0.2 if r[4] else 0,
            message=f"Possible tracking break on {r[1]}: conversions dropped from {r[4]:.0f} to {r[3]:.0f} while clicks stable",
            data={"drop_date": str(r[1]), "prior_conv": r[4], "current_conv": r[3]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Low Quality Scores ──
# Research: QS < 5 on keywords with meaningful spend costs 60%+ more CPC (TwoSquares, Geddes)

def detect_low_quality_scores(db: Database) -> list[Signal]:
    """Flag keywords with QS < 5 and significant weekly spend (>$200)."""
    rows = db.fetchall("""
        SELECT account_id, keyword_id, keyword_text, quality_score,
               cost_micros, impressions, match_type
        FROM keyword_metrics
        WHERE quality_score IS NOT NULL
          AND quality_score < 5
          AND cost_micros > 200000000
          AND impressions > 100
        ORDER BY cost_micros DESC
        LIMIT 50
    """)
    signals = []
    for r in rows:
        cost = r[4] / 1_000_000
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], domain=PatternDomain.NON_BRANDED_SEARCH,
            signal_type="low_quality_score", severity=Severity.WARNING,
            value=float(r[3]), threshold=5.0,
            message=f"Keyword '{r[2]}' has QS {r[3]} with ${cost:.0f} spend — paying ~60% CPC premium",
            data={"keyword_id": r[1], "keyword_text": r[2], "qs": r[3], "cost": cost, "match_type": r[6]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: CPA Spikes ──
# Research: CPA rising >3x historical average = investigate (Vallaeys Rule Engine)

def detect_cpa_spikes(db: Database) -> list[Signal]:
    """Detect campaigns where recent CPA exceeds N× their 30-day average.

    Thresholds: config/thresholds.yaml → cpa_spike.
    """
    th = effective_thresholds("cpa_spike")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed(f"""
        WITH recent AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(cost_micros) / NULLIF(sum(conversions), 0) as recent_cpa,
                   sum(conversions) as recent_conv,
                   count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) as recent_active_days,
                   max(cost_micros) / NULLIF(sum(cost_micros), 0) as recent_max_day_share
            FROM daily_metrics
            WHERE date >= current_date - {int(th['recent_window_days'])}
            GROUP BY account_id, campaign_id, campaign_name
            HAVING sum(conversions) >= {float(th['recent_conv_min'])}
               AND count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) >= {int(th['recent_active_days_min'])}
               AND max(cost_micros) / NULLIF(sum(cost_micros), 0) <= {float(th['max_single_day_share_max'])}
        ),
        baseline AS (
            SELECT account_id, campaign_id,
                   sum(cost_micros) / NULLIF(sum(conversions), 0) as baseline_cpa
            FROM daily_metrics
            WHERE date >= current_date - {int(th['baseline_window_days'])}
              AND date < current_date - {int(th['recent_window_days'])}
            GROUP BY account_id, campaign_id
            HAVING sum(conversions) > {float(th['baseline_conv_min'])}
        )
        SELECT r.account_id, r.campaign_id, r.campaign_name,
               r.recent_cpa / 1000000.0 as recent_cpa_dollars,
               b.baseline_cpa / 1000000.0 as baseline_cpa_dollars
        FROM recent r
        JOIN baseline b ON r.account_id = b.account_id AND r.campaign_id = b.campaign_id
        -- Phase 2.5: widen the spike threshold on high-CPA-volatility campaigns
        -- (×1.5) and tighten on stable ones (×0.7); 1.0 when no trend computed.
        LEFT JOIN campaign_trends ct ON ct.account_id = r.account_id
              AND ct.campaign_id = r.campaign_id AND ct.metric = 'cpa' AND ct.window_days = 30
        WHERE r.recent_cpa > b.baseline_cpa * {float(th['recent_cpa_multiplier'])}
                             * COALESCE(ct.threshold_multiplier, 1.0)
    """, anchor))
    signals = []
    mult = th['recent_cpa_multiplier']
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="cpa_spike", severity=Severity.CRITICAL,
            value=r[3], threshold=r[4] * mult,
            message=f"Campaign '{r[2]}' CPA spiked to ${r[3]:.2f} ({mult:g}x+ baseline of ${r[4]:.2f})",
            data={"campaign_id": r[1], "recent_cpa": r[3], "baseline_cpa": r[4]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Impression Share Loss ──
# Research: budget-lost IS > 20% = under-spending opportunity

def detect_impression_share_loss(db: Database) -> list[Signal]:
    """Flag campaigns losing >X% impression share to budget with meaningful spend.

    Thresholds: config/thresholds.yaml → budget_limited_is.
    """
    th = effective_thresholds("budget_limited_is")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed(f"""
        SELECT account_id, campaign_id, campaign_name,
               avg(search_budget_lost_is) as avg_budget_lost,
               avg(search_rank_lost_is) as avg_rank_lost,
               avg(search_impression_share) as avg_is
        FROM daily_metrics
        WHERE date >= current_date - {int(th['window_days'])}
          AND search_budget_lost_is IS NOT NULL
        GROUP BY account_id, campaign_id, campaign_name
        HAVING avg(search_budget_lost_is) > {float(th['avg_budget_lost_is_min'])}
           AND sum(cost_micros) > {int(th['total_cost_micros_min'])}
           AND sum(conversions) >= {float(th['min_conv_in_window'])}
    """, anchor))
    signals = []
    bl_min = th['avg_budget_lost_is_min']
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="budget_limited_is", severity=Severity.WARNING,
            value=r[3], threshold=bl_min,
            message=f"Campaign '{r[2]}' losing {r[3]:.0%} impression share to budget (IS = {r[5]:.0%})",
            data={"campaign_id": r[1], "budget_lost_is": r[3], "rank_lost_is": r[4], "avg_is": r[5]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: CVR Anomalies ──
# Research: CVR drop >30% week-over-week = investigate (landing page or tracking issue)

def detect_cvr_anomalies(db: Database) -> list[Signal]:
    """Detect campaigns with CVR dropping >X% week-over-week with volume floor.

    Thresholds: config/thresholds.yaml → cvr_drop.
    """
    th = effective_thresholds("cvr_drop")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    cur_w = int(th['current_window_days'])
    pri_w = int(th['prior_window_days'])
    window = cur_w + pri_w
    rows = db.fetchall(windowed(f"""
        WITH weekly AS (
            SELECT account_id, campaign_id, campaign_name,
                   CASE WHEN date >= current_date - {cur_w} THEN 'current' ELSE 'prior' END as period,
                   sum(conversions) as conv,
                   sum(clicks) as clicks
            FROM daily_metrics
            WHERE date >= current_date - {window}
            GROUP BY account_id, campaign_id, campaign_name,
                     CASE WHEN date >= current_date - {cur_w} THEN 'current' ELSE 'prior' END
        )
        SELECT c.account_id, c.campaign_id, c.campaign_name,
               c.conv / NULLIF(c.clicks, 0) as current_cvr,
               p.conv / NULLIF(p.clicks, 0) as prior_cvr
        FROM weekly c
        JOIN weekly p ON c.account_id = p.account_id AND c.campaign_id = p.campaign_id
        WHERE c.period = 'current' AND p.period = 'prior'
          AND p.clicks > {int(th['prior_clicks_min'])}
          AND c.clicks > {int(th['current_clicks_min'])}
          AND p.conv > {float(th['prior_conv_min'])}
          AND p.conv / NULLIF(p.clicks, 0) > {float(th['prior_cvr_min'])}
          AND c.conv / NULLIF(c.clicks, 0) < p.conv / NULLIF(p.clicks, 0) * {float(th['cvr_drop_ratio'])}
    """, anchor))
    signals = []
    ratio = th['cvr_drop_ratio']
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.LANDING_PAGE,
            signal_type="cvr_drop", severity=Severity.WARNING,
            value=r[3] or 0, threshold=(r[4] or 0) * ratio,
            message=f"Campaign '{r[2]}' CVR dropped from {(r[4] or 0):.1%} to {(r[3] or 0):.1%} week-over-week",
            data={"campaign_id": r[1], "current_cvr": r[3], "prior_cvr": r[4]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Brand/Non-Brand ROAS Contamination ──
# Research: Brand ROAS >10x while non-brand <2x in blended reporting = inflated metrics

def detect_brand_nonbrand_contamination(db: Database) -> list[Signal]:
    """Detect accounts where blended ROAS co-occurs with low non-brand ROAS.

    Thresholds load from config/thresholds.yaml (with vertical/tier overrides).
    Inline guards suppress obvious false positives the harness flagged:
      - low non-brand conversion volume → ROAS estimate is statistical noise
      - implausibly high brand ROAS    → likely value-inflation, not contamination
      - naming heuristic fails          → 'brand' campaign isn't actually brand
    When a guard fires, we emit `roas_contamination_unsafe` instead of suppressing
    silently, so the engine remains observable.
    """
    from brightmatter.thresholds import effective_thresholds
    from brightmatter.validation.brand_nonbrand import (
        brand_token_pct_per_campaign,
        brand_tokens_for_account,
    )

    # Pull candidates with a permissive SQL pass — apply per-account thresholds
    # in Python so vertical/tier overrides can tighten or loosen as configured.
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    candidates = db.fetchall(windowed("""
        WITH by_type AS (
            SELECT dm.account_id, dm.campaign_name,
                   CASE WHEN lower(dm.campaign_name) LIKE '%brand%' THEN 'brand' ELSE 'nonbrand' END as label,
                   sum(dm.conversion_value) as value,
                   sum(dm.cost_micros) / 1000000.0 as cost,
                   sum(dm.conversions) as convs
            FROM daily_metrics dm
            WHERE dm.date >= current_date - 30
            GROUP BY dm.account_id, dm.campaign_name,
                     CASE WHEN lower(dm.campaign_name) LIKE '%brand%' THEN 'brand' ELSE 'nonbrand' END
        ),
        account_rollup AS (
            SELECT account_id,
                   sum(CASE WHEN label = 'brand'    THEN value ELSE 0 END) as brand_value,
                   sum(CASE WHEN label = 'brand'    THEN cost  ELSE 0 END) as brand_cost,
                   sum(CASE WHEN label = 'brand'    THEN convs ELSE 0 END) as brand_convs,
                   sum(CASE WHEN label = 'nonbrand' THEN value ELSE 0 END) as nonbrand_value,
                   sum(CASE WHEN label = 'nonbrand' THEN cost  ELSE 0 END) as nonbrand_cost,
                   sum(CASE WHEN label = 'nonbrand' THEN convs ELSE 0 END) as nonbrand_convs,
                   sum(value) as total_value,
                   sum(cost)  as total_cost
            FROM by_type
            GROUP BY account_id
        )
        SELECT ar.account_id, a.business_type, a.spend_tier, a.vertical, a.account_name,
               ar.brand_value, ar.brand_cost, ar.brand_convs,
               ar.nonbrand_value, ar.nonbrand_cost, ar.nonbrand_convs,
               ar.total_value, ar.total_cost
        FROM account_rollup ar
        LEFT JOIN accounts a USING (account_id)
        WHERE ar.brand_cost > 0 AND ar.nonbrand_cost > 0
    """, anchor))

    signals: list[Signal] = []
    for (acct_id, biz_type, spend_tier, vertical, acct_name,
         b_val, b_cost, b_convs,
         nb_val, nb_cost, nb_convs,
         tot_val, tot_cost) in candidates:

        th = effective_thresholds(
            "brand_nonbrand_contamination",
            business_type=biz_type, spend_tier=spend_tier, vertical=vertical,
        )
        if th is None:
            continue  # override said skip (e.g., lead_gen)

        if b_cost < th["min_brand_cost_30d"] or nb_cost < th["min_nonbrand_cost_30d"]:
            continue

        brand_roas    = (b_val / b_cost)   if b_cost   else 0
        nonbrand_roas = (nb_val / nb_cost) if nb_cost  else 0
        blended_roas  = (tot_val / tot_cost) if tot_cost else 0

        # Core threshold gate
        if not (brand_roas    > th["brand_roas_min"]
                and nonbrand_roas < th["nonbrand_roas_max"]
                and blended_roas  > th["blended_roas_min"]):
            continue

        # Inline disconfirmation guards — failing any → unsafe variant
        guard_failures: list[str] = []
        if (nb_convs or 0) < th["min_nonbrand_conversions_30d"]:
            guard_failures.append(
                f"non-brand has only {nb_convs:.0f} convs in 30d "
                f"(<{th['min_nonbrand_conversions_30d']}); ROAS is statistical noise"
            )
        if brand_roas > th["brand_roas_max"]:
            guard_failures.append(
                f"brand ROAS {brand_roas:.1f}x exceeds plausibility cap "
                f"({th['brand_roas_max']}x); likely value inflation, not contamination"
            )

        # Naming-heuristic check — only when keyword data is present
        tokens = brand_tokens_for_account(acct_name or "")
        if tokens:
            pct_by_campaign = brand_token_pct_per_campaign(db, acct_id, tokens)
            mislabeled = []
            for name, pct in pct_by_campaign.items():
                if "brand" in name.lower() and pct < th["brand_token_match_pct_min"]:
                    mislabeled.append(f"'{name}' has {pct:.0%} brand-token kws")
            if mislabeled:
                guard_failures.append(
                    "naming heuristic unreliable: " + "; ".join(mislabeled[:2])
                )

        common_data = {
            "brand_roas":    brand_roas,
            "nonbrand_roas": nonbrand_roas,
            "blended_roas":  blended_roas,
            "brand_convs":   b_convs,
            "nonbrand_convs": nb_convs,
            "thresholds_used": th,
            "business_type": biz_type,
        }

        if guard_failures:
            signals.append(Signal(
                signal_id=_id(), account_id=acct_id,
                domain=PatternDomain.BRANDED_SEARCH,
                signal_type="roas_contamination_unsafe", severity=Severity.INFO,
                value=blended_roas, threshold=th["blended_roas_min"],
                message=(
                    f"Pattern threshold met (blended {blended_roas:.1f}x, "
                    f"non-brand {nonbrand_roas:.1f}x, brand {brand_roas:.1f}x) but "
                    f"{len(guard_failures)} disconfirmation guard(s) caught it: "
                    + " | ".join(guard_failures)
                ),
                data={**common_data, "guard_failures": guard_failures},
                detected_at=_now(),
            ))
        else:
            signals.append(Signal(
                signal_id=_id(), account_id=acct_id,
                domain=PatternDomain.BRANDED_SEARCH,
                signal_type="roas_contamination", severity=Severity.WARNING,
                value=blended_roas, threshold=th["blended_roas_min"],
                message=(
                    f"Blended ROAS {blended_roas:.1f}x co-occurs with non-brand "
                    f"ROAS of {nonbrand_roas:.1f}x (brand ROAS = {brand_roas:.1f}x)"
                ),
                data=common_data,
                detected_at=_now(),
            ))
    return signals


# ── Detector: PMax Channel Imbalance ──
# Research: Ecommerce PMax should be 60-80% Shopping; heavy Display/YouTube = problem

def detect_pmax_channel_imbalance(db: Database) -> list[Signal]:
    """Flag PMax campaigns in ecommerce accounts with low Shopping allocation.
    Note: PMax channel breakdown requires asset group reporting; this is a proxy
    using overall PMax vs Shopping campaign spend ratios at the account level."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed("""
        WITH spend_by_type AS (
            SELECT dm.account_id,
                   sum(CASE WHEN dm.campaign_type = 'PERFORMANCE_MAX' THEN dm.cost_micros ELSE 0 END) as pmax_spend,
                   sum(CASE WHEN dm.campaign_type = 'SHOPPING' THEN dm.cost_micros ELSE 0 END) as shopping_spend,
                   sum(dm.cost_micros) as total_spend
            FROM daily_metrics dm
            WHERE dm.date >= current_date - 30
            GROUP BY dm.account_id
            HAVING sum(CASE WHEN dm.campaign_type = 'PERFORMANCE_MAX' THEN dm.cost_micros ELSE 0 END) > 0
        )
        SELECT s.account_id, s.pmax_spend, s.shopping_spend, s.total_spend,
               a.business_type
        FROM spend_by_type s
        JOIN accounts a ON s.account_id = a.account_id
        WHERE a.business_type = 'ecommerce'
          AND s.pmax_spend > s.total_spend * 0.5
          AND s.shopping_spend < s.pmax_spend * 0.3
    """, anchor))
    signals = []
    for r in rows:
        pmax_pct = r[1] / r[3] if r[3] else 0
        signals.append(Signal(
            signal_id=_id(), account_id=r[0],
            domain=PatternDomain.PERFORMANCE_MAX,
            signal_type="pmax_dominance_no_shopping", severity=Severity.WARNING,
            value=pmax_pct, threshold=0.5,
            message=f"Ecommerce account running {pmax_pct:.0%} PMax with minimal Shopping — may indicate feed issues",
            data={"pmax_spend": r[1] / 1e6, "shopping_spend": r[2] / 1e6, "total_spend": r[3] / 1e6},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Auto-Applied Changes ──
# Research: Causal Chain #11 — auto-applied recs can silently degrade performance

def detect_auto_applied_changes(db: Database) -> list[Signal]:
    """Flag accounts with auto-applied changes in the threshold window.

    Thresholds: config/thresholds.yaml → auto_applied_changes.
    """
    th = effective_thresholds("auto_applied_changes")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    window = int(th['window_days'])
    crit = int(th['critical_count'])
    min_changes = int(th['min_changes'])
    rows = db.fetchall(windowed(f"""
        SELECT account_id, count(*) as auto_count,
               min(change_timestamp) as earliest,
               max(change_timestamp) as latest
        FROM change_events
        WHERE actor = 'auto_applied'
          AND change_timestamp >= current_date - {window}
        GROUP BY account_id
        HAVING count(*) >= {min_changes}
        ORDER BY count(*) DESC
    """, anchor))
    signals = []
    for r in rows:
        severity = Severity.CRITICAL if r[1] > crit else Severity.WARNING
        signals.append(Signal(
            signal_id=_id(), account_id=r[0],
            domain=PatternDomain.CAMPAIGN_STRUCTURE,
            signal_type="auto_applied_changes", severity=severity,
            value=float(r[1]), threshold=1.0,
            message=f"{r[1]} auto-applied changes detected in last {window} days — review for unintended modifications",
            data={"count": r[1], "earliest": str(r[2]), "latest": str(r[3])},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Budget-Capped Campaigns ──
# Research: budget_lost_is > budget means campaigns can't spend what they want

def detect_budget_capped_campaigns(db: Database) -> list[Signal]:
    """Flag campaigns consistently hitting budget cap.

    Thresholds: config/thresholds.yaml → budget_capped.
    """
    th = effective_thresholds("budget_capped")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    window = int(th['window_days'])
    bl_min = float(th['avg_budget_lost_is_min'])
    # Aggregate over the full window so sum(conversions) counts every day, not
    # only capped days; days_capped / avg loss are restricted to capped days
    # via CASE. The conversion floor keeps the signal to caps that actually
    # gate meaningful volume (the harness's only functional confirming test,
    # since daily_budget_micros is unavailable for the utilization check).
    rows = db.fetchall(windowed(f"""
        SELECT account_id, campaign_id, campaign_name,
               avg(CASE WHEN search_budget_lost_is > {bl_min}
                        THEN search_budget_lost_is END) as avg_budget_lost,
               count(CASE WHEN search_budget_lost_is > {bl_min} THEN 1 END) as days_checked
        FROM daily_metrics
        WHERE date >= current_date - {window}
          AND search_budget_lost_is IS NOT NULL
        GROUP BY account_id, campaign_id, campaign_name
        HAVING count(CASE WHEN search_budget_lost_is > {bl_min} THEN 1 END) >= {int(th['min_days_capped'])}
           AND sum(conversions) >= {float(th['min_conv_in_window'])}
    """, anchor))
    signals = []
    threshold = th['avg_budget_lost_is_min']
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="budget_capped", severity=Severity.INFO,
            value=r[3], threshold=threshold,
            message=f"Campaign '{r[2]}' budget-capped for {r[4]} of last {window} days (avg {r[3]:.0%} IS lost to budget)",
            data={"campaign_id": r[1], "avg_budget_lost_is": r[3], "days_capped": r[4]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Bidding Anti-Patterns ──
# Research: Broad match + manual CPC = waste; tROAS with < 50 conv/month = insufficient data

def detect_bidding_antipatterns(db: Database) -> list[Signal]:
    """Flag campaigns on tCPA/tROAS without enough conversions to optimize.

    Thresholds: config/thresholds.yaml → insufficient_conversions_for_strategy.
    """
    th = effective_thresholds("insufficient_conversions_for_strategy")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    strategies_in = ", ".join(f"'{s}'" for s in th.get("strategies", []))
    # Gate out campaigns that are paused (the strategy isn't even running) or
    # too new to have accumulated a month of conversions — both produce low
    # counts for reasons unrelated to a misconfigured strategy (harness T1/T4).
    rows = db.fetchall(windowed(f"""
        WITH agg AS (
            SELECT account_id, campaign_id, campaign_name, bidding_strategy,
                   sum(conversions) as monthly_conv,
                   count(CASE WHEN status = 'ENABLED' THEN 1 END) as enabled_days,
                   count(*) as total_days
            FROM daily_metrics
            WHERE date >= current_date - {int(th['window_days'])}
              AND bidding_strategy IN ({strategies_in})
            GROUP BY account_id, campaign_id, campaign_name, bidding_strategy
            HAVING sum(conversions) < {float(th['monthly_conv_min'])}
               AND count(CASE WHEN status = 'ENABLED' THEN 1 END) > count(*) * 0.5
        ),
        age AS (
            SELECT account_id, campaign_id, (max(date) - min(date)) + 1 as age_days
            FROM daily_metrics
            GROUP BY account_id, campaign_id
        )
        SELECT agg.account_id, agg.campaign_id, agg.campaign_name,
               agg.bidding_strategy, agg.monthly_conv
        FROM agg
        JOIN age USING (account_id, campaign_id)
        WHERE age.age_days >= {int(th['min_campaign_age_days'])}
    """, anchor))
    signals = []
    minimum = th['monthly_conv_min']
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="insufficient_conversions_for_strategy", severity=Severity.WARNING,
            value=r[4], threshold=float(minimum),
            message=f"Campaign '{r[2]}' using {r[3]} with only {r[4]:.0f} conv/month (need {minimum:g}+ for reliable optimization)",
            data={"campaign_id": r[1], "strategy": r[3], "monthly_conversions": r[4]},
            detected_at=_now(),
        ))
    return signals


# ── Wave 1 Detectors ──

# ── Detector: Suspicious Primary Conversions ──
# Research: Vallaeys — 47% of stuck campaigns trace to tracking. Rhodes checks first.

_SUSPICIOUS_CATEGORIES = {"PAGE_VIEW", "DEFAULT", "DOWNLOAD", "ADD_TO_CART", "BEGIN_CHECKOUT"}
_LEGIT_CATEGORIES = {"PURCHASE", "LEAD", "SIGNUP", "SUBSCRIBE_PAID", "BOOK_APPOINTMENT",
                     "SUBMIT_LEAD_FORM", "REQUEST_QUOTE", "GET_DIRECTIONS", "IMPORTED_LEAD"}

def detect_suspicious_primary_conversions(db: Database) -> list[Signal]:
    """Flag accounts whose primary conversion actions are micro-conversions."""
    try:
        rows = db.fetchall("""
            SELECT account_id, action_id, action_name, action_type, category
            FROM conversion_actions
            WHERE primary_for_goal = true
              AND status = 'ENABLED'
        """)
    except Exception:
        return []

    signals = []
    seen_accounts = set()
    for r in rows:
        acct, aid, name, atype, cat = r
        if acct in seen_accounts:
            continue
        cat_suspicious = cat in _SUSPICIOUS_CATEGORIES
        name_hints = any(h in (name or "").lower() for h in
                        ["page view", "pageview", "scroll", "session start", "time on site",
                         "all pages", "site visit"])
        if cat_suspicious or name_hints:
            seen_accounts.add(acct)
            signals.append(Signal(
                signal_id=_id(), account_id=acct,
                domain=PatternDomain.LANDING_PAGE,
                signal_type="suspicious_primary_conversion", severity=Severity.CRITICAL,
                value=1.0, threshold=0.0,
                message=f"Primary conversion '{name}' (category={cat}) is a micro-conversion — Smart Bidding optimizes for this instead of real conversions",
                data={"action_id": aid, "action_name": name, "type": atype, "category": cat},
                detected_at=_now(),
            ))
    return signals


# ── Detector: Duplicate Primary Conversions ──
# Research: Multiple primary actions = double-counting conversions

def detect_duplicate_primary_conversions(db: Database) -> list[Signal]:
    """Flag accounts with N+ primary conversion actions (likely double-counting).

    Thresholds: config/thresholds.yaml → duplicate_primary_conversions.
    """
    th = effective_thresholds("duplicate_primary_conversions")
    same_cat_min = int(th['same_category_min'])
    cvr_min = float(th['inflation_cvr_min'])
    vpc_max = float(th['inflation_value_per_conv_max'])
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    try:
        rows = db.fetchall(f"""
            SELECT account_id, category, count(*) as cat_count,
                   string_agg(action_name, ', ') as names
            FROM conversion_actions
            WHERE primary_for_goal = true AND status = 'ENABLED'
            GROUP BY account_id, category
            HAVING count(*) >= {same_cat_min}
        """)
    except Exception:
        return []

    signals = []
    seen: set[str] = set()
    for acct, category, cat_count, names in rows:
        if acct in seen:
            continue
        # Same-category duplication is only a problem if it actually inflates
        # the numbers. Corroborate with performance: implausibly high account
        # CVR (multi-counting) or near-zero value-per-conversion (junk convs).
        perf = db.fetchone(windowed("""
            SELECT sum(conversions), sum(clicks), sum(conversion_value)
            FROM daily_metrics
            WHERE account_id = ? AND date >= current_date - 30
        """, anchor), [acct])
        conv, clicks, value = (perf or (0, 0, 0))
        conv, clicks, value = (conv or 0, clicks or 0, value or 0)
        cvr = (conv / clicks) if clicks else 0
        vpc = (value / conv) if conv else None
        high_cvr = cvr > cvr_min
        low_vpc = value > 0 and vpc is not None and vpc < vpc_max
        if not (high_cvr or low_vpc):
            continue
        seen.add(acct)
        reason = (f"account CVR {cvr:.0%} is implausibly high" if high_cvr
                  else f"value/conversion is ${vpc:.2f}")
        signals.append(Signal(
            signal_id=_id(), account_id=acct,
            domain=PatternDomain.LANDING_PAGE,
            signal_type="duplicate_primary_conversions", severity=Severity.WARNING,
            value=float(cat_count), threshold=float(same_cat_min),
            message=f"{cat_count} primary '{category}' conversion actions (same goal) — "
                    f"{reason}, likely double-counting: {names[:80]}",
            data={"category": category, "same_category_count": cat_count,
                  "action_names": names, "account_cvr_30d": round(cvr, 4),
                  "value_per_conv": round(vpc, 2) if vpc is not None else None},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Missing Conversion Value ──
# Research: Ecommerce accounts without value tracking can't use tROAS

def detect_missing_conversion_value(db: Database) -> list[Signal]:
    """Flag accounts with conversions but zero conversion value (missing value tracking)."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed("""
        SELECT account_id,
               sum(conversions) as total_conv,
               sum(conversion_value) as total_value,
               sum(cost_micros) / 1000000.0 as total_cost
        FROM daily_metrics
        WHERE date >= current_date - 30
        GROUP BY account_id
        HAVING sum(conversions) > 50
           AND sum(conversion_value) = 0
           AND sum(cost_micros) > 5000000000
    """, anchor))
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0],
            domain=PatternDomain.LANDING_PAGE,
            signal_type="missing_conversion_value", severity=Severity.WARNING,
            value=0.0, threshold=1.0,
            message=f"{r[1]:.0f} conversions with $0 value on ${r[3]:,.0f} spend — cannot use value-based bidding (tROAS)",
            data={"conversions": r[1], "value": r[2], "cost": r[3]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Over-Segmentation ──
# Research: smec says <30 conv/month per campaign = unreliable. Lolk says 100+.

def detect_over_segmentation(db: Database) -> list[Signal]:
    """Flag accounts with many campaigns starving for conversion data.

    Thresholds: config/thresholds.yaml → over_segmentation.
    """
    th = effective_thresholds("over_segmentation")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed(f"""
        WITH campaign_conv AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(conversions) as monthly_conv
            FROM daily_metrics
            WHERE date >= current_date - {int(th['window_days'])}
              AND status = 'ENABLED'
            GROUP BY account_id, campaign_id, campaign_name
        ),
        account_summary AS (
            SELECT account_id,
                   count(*) as total_campaigns,
                   sum(monthly_conv) as total_conv,
                   sum(CASE WHEN monthly_conv < {float(th['per_campaign_conv_min'])} THEN 1 ELSE 0 END) as starving_campaigns,
                   sum(CASE WHEN monthly_conv < {float(th['per_campaign_conv_min'])} THEN monthly_conv ELSE 0 END) as starving_conv
            FROM campaign_conv
            WHERE monthly_conv > 0
            GROUP BY account_id
            HAVING count(*) >= {int(th['account_campaigns_min'])}
               AND sum(monthly_conv) > {float(th['account_total_conv_min'])}
        )
        SELECT account_id, total_campaigns, total_conv,
               starving_campaigns, starving_conv,
               starving_campaigns * 1.0 / total_campaigns as starving_pct
        FROM account_summary
        WHERE starving_campaigns * 1.0 / total_campaigns > {float(th['starving_share_min'])}
    """, anchor))
    geo_max = float(th['intentional_geo_share_max'])
    tb_max = float(th['intentional_type_brand_share_max'])
    per_camp_min = float(th['per_campaign_conv_min'])
    signals = []
    for r in rows:
        acct = r[0]
        # Suppress when the starving campaigns are predominantly geo- or
        # type/brand-named: that's a deliberate split, not accidental
        # fragmentation (harness T1/T2). Same starving definition as the query.
        starving_names = [row[0] for row in db.fetchall(windowed(f"""
            SELECT campaign_name
            FROM daily_metrics
            WHERE account_id = ? AND date >= current_date - {int(th['window_days'])}
              AND status = 'ENABLED'
            GROUP BY campaign_id, campaign_name
            HAVING sum(conversions) < {per_camp_min} AND sum(conversions) > 0
        """, anchor), [acct])]
        geo_frac, tb_frac = split_fractions(starving_names)
        if geo_frac >= geo_max or tb_frac >= tb_max:
            continue
        signals.append(Signal(
            signal_id=_id(), account_id=acct,
            domain=PatternDomain.CAMPAIGN_STRUCTURE,
            signal_type="over_segmentation", severity=Severity.WARNING,
            value=r[5], threshold=0.5,
            message=f"{r[3]}/{r[1]} campaigns have <30 conv/month ({r[5]:.0%} starving) despite {r[2]:.0f} total — consider consolidation",
            data={"total_campaigns": r[1], "total_conv": r[2], "starving": r[3],
                  "starving_pct": r[5], "starving_geo_frac": round(geo_frac, 2),
                  "starving_type_brand_frac": round(tb_frac, 2)},
            detected_at=_now(),
        ))
    return signals


# ── Wave 2 Detectors ──

# ── Detector: Missing Brand Separation ──
# Research: Geddes, Lolk, Williams, Rhodes — brand/non-brand split is non-negotiable

def detect_missing_brand_separation(db: Database) -> list[Signal]:
    """Flag accounts with no dedicated brand campaign despite having brand-like performance."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed("""
        WITH campaign_perf AS (
            SELECT account_id, campaign_id, campaign_name, campaign_type,
                   sum(conversions) / NULLIF(sum(clicks), 0) as cvr,
                   sum(cost_micros) as cost
            FROM daily_metrics
            WHERE date >= current_date - 30
              AND campaign_type = 'SEARCH'
              AND status = 'ENABLED'
            GROUP BY account_id, campaign_id, campaign_name, campaign_type
            HAVING sum(clicks) > 100
        ),
        account_brand AS (
            SELECT account_id,
                   max(CASE WHEN lower(campaign_name) LIKE '%brand%' THEN 1 ELSE 0 END) as has_brand_campaign,
                   max(cvr) as max_cvr,
                   count(*) as search_campaigns
            FROM campaign_perf
            GROUP BY account_id
            HAVING count(*) >= 2
        )
        SELECT account_id, has_brand_campaign, max_cvr, search_campaigns
        FROM account_brand
        WHERE has_brand_campaign = 0
          AND max_cvr > 0.10
    """, anchor))
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0],
            domain=PatternDomain.BRANDED_SEARCH,
            signal_type="missing_brand_separation", severity=Severity.WARNING,
            value=r[2], threshold=0.10,
            message=f"No brand campaign found but {r[3]} Search campaigns exist with max CVR {r[2]:.0%} — brand traffic likely mixed into non-brand",
            data={"search_campaigns": r[3], "max_cvr": r[2]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Campaign Type Gaps ──
# Research: ecommerce needs Shopping; all accounts benefit from Search + PMax

def detect_campaign_type_gaps(db: Database) -> list[Signal]:
    """Flag accounts missing expected campaign types based on their profile."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed("""
        SELECT account_id,
               count(DISTINCT CASE WHEN campaign_type = 'SEARCH' THEN campaign_id END) as search_count,
               count(DISTINCT CASE WHEN campaign_type = 'PERFORMANCE_MAX' THEN campaign_id END) as pmax_count,
               count(DISTINCT CASE WHEN campaign_type = 'SHOPPING' THEN campaign_id END) as shopping_count,
               count(DISTINCT campaign_id) as total,
               sum(cost_micros) / 1000000.0 as total_spend
        FROM daily_metrics
        WHERE date >= current_date - 30
          AND status = 'ENABLED'
        GROUP BY account_id
        HAVING sum(cost_micros) > 10000000000
    """, anchor))
    signals = []
    for r in rows:
        acct, search, pmax, shopping, total, spend = r
        if search == 0 and spend > 10000:
            signals.append(Signal(
                signal_id=_id(), account_id=acct,
                domain=PatternDomain.CAMPAIGN_STRUCTURE,
                signal_type="no_search_campaigns", severity=Severity.INFO,
                value=0, threshold=1,
                message=f"No Search campaigns with ${spend:,.0f} spend — relying entirely on PMax/Shopping for all query matching",
                data={"search": search, "pmax": pmax, "shopping": shopping, "spend": spend},
                detected_at=_now(),
            ))
        if pmax == 0 and search > 0 and spend > 25000:
            signals.append(Signal(
                signal_id=_id(), account_id=acct,
                domain=PatternDomain.CAMPAIGN_STRUCTURE,
                signal_type="no_pmax_campaigns", severity=Severity.INFO,
                value=0, threshold=1,
                message=f"No PMax campaigns with ${spend:,.0f} spend — may be missing cross-channel reach",
                data={"search": search, "pmax": pmax, "shopping": shopping, "spend": spend},
                detected_at=_now(),
            ))
    return signals


# ── Detector: Broad Match Without Smart Bidding ──
# Research: Vallaeys, ALM Corp — broad + manual CPC = budget waste

def detect_broad_without_smart_bidding(db: Database) -> list[Signal]:
    """Flag campaigns using broad match keywords with manual bidding."""
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    try:
        rows = db.fetchall(windowed("""
            SELECT kc.account_id, kc.campaign_id, kc.campaign_name,
                   kc.broad_count, kc.keyword_count,
                   dm.bidding_strategy
            FROM keyword_counts kc
            JOIN (
                SELECT DISTINCT account_id, campaign_id, bidding_strategy
                FROM daily_metrics
                WHERE date >= current_date - 7
            ) dm ON kc.account_id = dm.account_id AND kc.campaign_id = dm.campaign_id
            WHERE kc.broad_count > 0
              AND dm.bidding_strategy IN ('MANUAL_CPC', 'MANUAL_CPM', 'MAXIMIZE_CLICKS')
        """, anchor))
    except Exception:
        return []
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.NON_BRANDED_SEARCH,
            signal_type="broad_without_smart_bidding", severity=Severity.WARNING,
            value=float(r[3]), threshold=0.0,
            message=f"Campaign '{r[2]}' has {r[3]} broad match keywords with {r[5]} bidding — broad needs Smart Bidding",
            data={"campaign_id": r[1], "broad_count": r[3], "strategy": r[5]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Low Negative Keyword Ratio ──
# Research: negative-to-active ratio should be 0.30-0.50 for healthy query control

def detect_low_negative_ratio(db: Database) -> list[Signal]:
    """Flag accounts with very few negative keywords relative to active keywords."""
    try:
        rows = db.fetchall("""
            SELECT account_id,
                   sum(keyword_count) as total_keywords,
                   sum(negative_count) as total_negatives,
                   sum(negative_count) * 1.0 / NULLIF(sum(keyword_count), 0) as ratio
            FROM keyword_counts
            WHERE keyword_count > 0
            GROUP BY account_id
            HAVING sum(keyword_count) > 20
               AND sum(negative_count) * 1.0 / sum(keyword_count) < 0.15
        """)
    except Exception:
        return []
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0],
            domain=PatternDomain.NON_BRANDED_SEARCH,
            signal_type="low_negative_ratio", severity=Severity.INFO,
            value=r[3] or 0, threshold=0.30,
            message=f"{r[2] or 0:.0f} negatives for {r[1]:.0f} keywords (ratio {(r[3] or 0):.0%}) — research says 0.30-0.50 is healthy",
            data={"keywords": r[1], "negatives": r[2], "ratio": r[3]},
            detected_at=_now(),
        ))
    return signals


# ── Wave 3 Detectors ──

# ── Detector: Missing Extensions ──
# Research: full extension coverage outperforms minimal coverage

_IMPORTANT_ASSET_TYPES = {"SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "CALL", "IMAGE", "PRICE", "PROMOTION"}

def detect_missing_extensions(db: Database) -> list[Signal]:
    """Flag accounts with fewer than 4 of 7 key extension types."""
    try:
        rows = db.fetchall("""
            SELECT account_id, count(DISTINCT asset_type) as type_count,
                   string_agg(DISTINCT asset_type, ', ') as types_present
            FROM asset_coverage
            GROUP BY account_id
        """)
    except Exception:
        return []

    signals = []
    for r in rows:
        present_types = set((r[2] or "").split(", "))
        important_present = present_types & _IMPORTANT_ASSET_TYPES
        missing = _IMPORTANT_ASSET_TYPES - present_types
        if len(important_present) < 4 and missing:
            signals.append(Signal(
                signal_id=_id(), account_id=r[0],
                domain=PatternDomain.CREATIVE,
                signal_type="missing_extensions", severity=Severity.INFO,
                value=float(len(important_present)), threshold=4.0,
                message=f"Only {len(important_present)}/7 key extension types present. Missing: {', '.join(sorted(missing))}",
                data={"present": list(important_present), "missing": list(missing)},
                detected_at=_now(),
            ))
    return signals


# ── Detector: Cross-Account Outlier ──
# Research: accounts whose CPA is >2 std dev from the peer group mean

def detect_cross_account_outlier(db: Database) -> list[Signal]:
    """Flag accounts whose CPA is far above their SEGMENT peers' CPA.

    Compares each account against the tightest peer group with enough members
    (vertical+tier -> vertical -> spend_tier -> global), so a high-CPA legal
    account isn't judged against low-CPA apparel. Thresholds:
    config/thresholds.yaml -> cross_account_cpa_outlier.
    """
    import statistics

    th = effective_thresholds("cross_account_cpa_outlier")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    window = int(th["window_days"])
    min_conv = float(th["min_conversions"])
    min_cost = int(th["min_cost_micros"])
    z_thr = float(th["z_threshold"])
    min_peers = int(th["min_peers"])

    rows = db.fetchall(windowed(f"""
        SELECT ap.account_id, ap.cpa, ap.cost, ap.conv,
               COALESCE(a.vertical, '') as vertical,
               COALESCE(a.spend_tier, '') as spend_tier
        FROM (
            SELECT account_id,
                   sum(cost_micros) / 1000000.0 as cost,
                   sum(conversions) as conv,
                   sum(cost_micros) / NULLIF(sum(conversions), 0) / 1000000.0 as cpa
            FROM daily_metrics
            WHERE date >= current_date - {window}
            GROUP BY account_id
            HAVING sum(conversions) > {min_conv} AND sum(cost_micros) > {min_cost}
        ) ap
        LEFT JOIN accounts a ON a.account_id = ap.account_id
        WHERE ap.cpa IS NOT NULL AND ap.cpa > 0
    """, anchor))

    perf = [{"account_id": r[0], "cpa": r[1], "cost": r[2], "conv": r[3],
             "vertical": r[4], "spend_tier": r[5]} for r in rows]

    # Fallback chain: use the most specific segment that has >= min_peers.
    # Empty vertical/tier strings are falsy, so those accounts skip that level.
    levels = [
        ("vertical+tier", lambda q, p: bool(p["vertical"]) and bool(p["spend_tier"])
            and q["vertical"] == p["vertical"] and q["spend_tier"] == p["spend_tier"]),
        ("vertical", lambda q, p: bool(p["vertical"]) and q["vertical"] == p["vertical"]),
        ("spend_tier", lambda q, p: bool(p["spend_tier"]) and q["spend_tier"] == p["spend_tier"]),
        ("global", lambda q, p: True),
    ]

    signals = []
    for p in perf:
        segment, peers = "global", [q["cpa"] for q in perf]
        for name, pred in levels:
            grp = [q["cpa"] for q in perf if pred(q, p)]
            if len(grp) >= min_peers:
                segment, peers = name, grp
                break
        if len(peers) < 2:
            continue
        mean = statistics.mean(peers)
        std = statistics.pstdev(peers)
        if std <= 0:
            continue
        z = (p["cpa"] - mean) / std
        if z <= z_thr:
            continue
        seg_label = (f"{p['vertical']}/{p['spend_tier']}" if segment == "vertical+tier"
                     else p["vertical"] if segment == "vertical"
                     else p["spend_tier"] if segment == "spend_tier"
                     else "all accounts")
        signals.append(Signal(
            signal_id=_id(), account_id=p["account_id"],
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="cross_account_cpa_outlier", severity=Severity.WARNING,
            value=p["cpa"], threshold=mean + z_thr * std,
            message=(f"CPA ${p['cpa']:,.2f} is {z:.1f}σ above the {seg_label} peer mean "
                     f"${mean:,.2f} (n={len(peers)} {segment} peers, {p['conv']:.0f} conv)"),
            data={"cpa": p["cpa"], "segment": segment, "segment_label": seg_label,
                  "peer_n": len(peers), "mean_cpa": mean, "std_cpa": std, "z_score": z,
                  "vertical": p["vertical"], "spend_tier": p["spend_tier"]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: PMax Low Conversion Volume ──
# Research: smec — PMax needs 30+ conv/month, 50-100 optimal

def detect_pmax_low_conversion_volume(db: Database) -> list[Signal]:
    """Flag PMax campaigns with insufficient conversions to optimize.

    Thresholds: config/thresholds.yaml → pmax_low_conv_volume.
    """
    th = effective_thresholds("pmax_low_conv_volume")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    minimum = th['monthly_conv_min']
    # Age gate: a PMax campaign still in its ramp hasn't had time to reach
    # 30 conv/month, so "insufficient volume to optimize" isn't yet a real
    # claim. Compute age from the campaign's full data history (any status),
    # matching harness T4, and require it to clear min_campaign_age_days.
    rows = db.fetchall(windowed(f"""
        WITH agg AS (
            SELECT account_id, campaign_id, campaign_name,
                   sum(conversions) as monthly_conv,
                   sum(cost_micros) / 1000000.0 as monthly_cost
            FROM daily_metrics
            WHERE date >= current_date - {int(th['window_days'])}
              AND campaign_type = 'PERFORMANCE_MAX'
              AND status = 'ENABLED'
            GROUP BY account_id, campaign_id, campaign_name
            HAVING sum(conversions) < {float(minimum)}
               AND sum(cost_micros) > {int(th['monthly_cost_micros_min'])}
               -- Exempt high-AOV PMax: with enough conversion VALUE, Smart
               -- Bidding can optimize on revenue despite a low count (harness T2).
               AND (sum(conversion_value) / NULLIF(sum(conversions), 0)
                        < {float(th['high_value_per_conv_exempt'])}
                    OR sum(conversions) < {float(th['high_value_conv_min'])})
        ),
        age AS (
            SELECT account_id, campaign_id,
                   (max(date) - min(date)) + 1 as age_days
            FROM daily_metrics
            GROUP BY account_id, campaign_id
        )
        SELECT agg.account_id, agg.campaign_id, agg.campaign_name,
               agg.monthly_conv, agg.monthly_cost
        FROM agg
        JOIN age USING (account_id, campaign_id)
        WHERE age.age_days >= {int(th['min_campaign_age_days'])}
    """, anchor))
    signals = []
    for r in rows:
        signals.append(Signal(
            signal_id=_id(), account_id=r[0], campaign_id=r[1],
            domain=PatternDomain.PERFORMANCE_MAX,
            signal_type="pmax_low_conv_volume", severity=Severity.WARNING,
            value=r[3], threshold=float(minimum),
            message=f"PMax '{r[2]}' has only {r[3]:.0f} conv/month on ${r[4]:,.0f} spend — needs {minimum:g}+ for Smart Bidding to optimize",
            data={"campaign_id": r[1], "monthly_conv": r[3], "monthly_cost": r[4]},
            detected_at=_now(),
        ))
    return signals


# ── Detector: PMax Conversion Inflation ──
# Research: PMax inherits all primary conversion actions by default and counts
# micro-conversions Search doesn't, inflating its apparent CVR/ROAS. Empirically
# found in LOCKLY (26K PMax vs 290 Search conversions). Compare PMax vs Search
# CVR within the same account: a large gap is the observable inflation signature.

def detect_pmax_conversion_inflation(db: Database) -> list[Signal]:
    """Flag accounts where PMax CVR is implausibly higher than Search CVR.

    PMax and Search bid in the same auctions for the same advertiser; PMax can
    convert somewhat higher (shopping/retargeting mix), but a multiple-x gap
    usually means PMax is counting conversion actions Search isn't.

    Thresholds: config/thresholds.yaml → pmax_conversion_inflation.
    """
    th = effective_thresholds("pmax_conversion_inflation")
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    rows = db.fetchall(windowed(f"""
        WITH agg AS (
            SELECT account_id, campaign_type,
                   sum(conversions) as conv, sum(clicks) as clk,
                   sum(conversion_value) as val
            FROM daily_metrics
            WHERE date >= current_date - {int(th['window_days'])}
              AND campaign_type IN ('PERFORMANCE_MAX', 'SEARCH')
            GROUP BY account_id, campaign_type
        )
        SELECT p.account_id,
               p.conv as pmax_conv, p.clk as pmax_clk, p.val as pmax_val,
               s.conv as search_conv, s.clk as search_clk, s.val as search_val,
               (p.conv / NULLIF(p.clk, 0)) as pmax_cvr,
               (s.conv / NULLIF(s.clk, 0)) as search_cvr
        FROM agg p
        JOIN agg s ON p.account_id = s.account_id
        WHERE p.campaign_type = 'PERFORMANCE_MAX' AND s.campaign_type = 'SEARCH'
          AND p.clk >= {int(th['min_pmax_clicks'])}
          AND s.clk >= {int(th['min_search_clicks'])}
          AND p.conv >= {float(th['min_pmax_conv'])}
          -- Search also needs enough conversions or its CVR (the ratio's
          -- denominator) is small-sample noise and the gap is spurious (T1/T4).
          AND s.conv >= {float(th['min_search_conv'])}
          AND (p.conv / NULLIF(p.clk, 0))
              >= {float(th['cvr_ratio_min'])} * (s.conv / NULLIF(s.clk, 0))
          AND (s.conv / NULLIF(s.clk, 0)) > 0
    """, anchor))
    signals = []
    ratio_min = th['cvr_ratio_min']
    for r in rows:
        acct, pconv, pclk, pval, sconv, sclk, sval, pcvr, scvr = r
        ratio = pcvr / scvr if scvr else 0.0
        signals.append(Signal(
            signal_id=_id(), account_id=acct,
            domain=PatternDomain.PERFORMANCE_MAX,
            signal_type="pmax_conversion_inflation", severity=Severity.WARNING,
            value=ratio, threshold=float(ratio_min),
            message=(f"PMax CVR {pcvr:.1%} is {ratio:.1f}x Search CVR {scvr:.1%} in the same account "
                     f"({pconv:.0f} PMax vs {sconv:.0f} Search conv) — PMax may be counting "
                     f"conversion actions Search isn't (micro-conversion inflation)"),
            data={"pmax_cvr": pcvr, "search_cvr": scvr, "cvr_ratio": ratio,
                  "pmax_conv": pconv, "search_conv": sconv,
                  "pmax_value_per_conv": (pval / pconv) if pconv else None,
                  "search_value_per_conv": (sval / sconv) if sconv else None},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Search Terms Waste ──
# Research: the #1 audit finding across every published checklist — spend on
# search terms that never convert. DATA DEPENDENCY: the `search_terms` table,
# populated by `ingest --search-terms` (search_term_view GAQL). Until that is
# ingested the table is empty and this detector produces no signals. SCAFFOLDED
# 2026-06: detector + harness are code-complete but UNVALIDATED against real
# search-term data — validate after the first search_term_view ingest.

def detect_search_terms_waste(db: Database) -> list[Signal]:
    """Flag campaigns where a material share of spend went to zero-conversion terms.

    Thresholds: config/thresholds.yaml → search_terms_waste.
    """
    th = effective_thresholds("search_terms_waste")
    min_term_cost = int(th['min_term_cost_micros'])
    min_term_impr = int(th['min_term_impressions'])
    min_total_waste = int(th['min_total_waste_micros'])
    waste_share_min = float(th['waste_share_min'])
    # A term counts as "wasted" when it has real exposure (>= min impressions),
    # meaningful spend (>= min cost), and zero conversions over the window.
    waste_pred = (f"st.conversions = 0 AND st.cost_micros >= {min_term_cost} "
                  f"AND st.impressions >= {min_term_impr}")
    try:
        rows = db.fetchall(f"""
            WITH latest AS (SELECT max(window_end) as w FROM search_terms),
            camp AS (
                SELECT st.account_id, st.campaign_id, st.campaign_name,
                       sum(st.cost_micros) as total_cost,
                       sum(CASE WHEN {waste_pred} THEN st.cost_micros ELSE 0 END) as waste_cost,
                       sum(CASE WHEN {waste_pred} THEN st.clicks ELSE 0 END) as waste_clicks,
                       count(CASE WHEN {waste_pred} THEN 1 END) as waste_terms
                FROM search_terms st, latest
                WHERE st.window_end = latest.w
                GROUP BY st.account_id, st.campaign_id, st.campaign_name
            )
            SELECT account_id, campaign_id, campaign_name,
                   total_cost, waste_cost, waste_clicks, waste_terms
            FROM camp
            WHERE waste_cost >= {min_total_waste}
              AND waste_cost >= {waste_share_min} * NULLIF(total_cost, 0)
              -- Enough clicks on the zero-conv terms that "never converts" is a
              -- real signal, not small-sample noise (harness T1).
              AND waste_clicks >= {int(th['min_waste_clicks'])}
            ORDER BY waste_cost DESC
        """)
    except Exception:
        # search_terms not yet ingested / table absent — no signals.
        return []
    signals = []
    for r in rows:
        acct, cid, cname, total_cost, waste_cost, waste_clicks, waste_terms = r
        share = (waste_cost / total_cost) if total_cost else 0.0
        signals.append(Signal(
            signal_id=_id(), account_id=acct, campaign_id=cid,
            domain=PatternDomain.NON_BRANDED_SEARCH,
            signal_type="search_terms_waste", severity=Severity.WARNING,
            value=waste_cost / 1_000_000, threshold=min_total_waste / 1_000_000,
            message=(f"Campaign '{cname}': ${waste_cost / 1e6:,.0f} ({share:.0%} of spend) on "
                     f"{waste_terms} zero-conversion search terms ({waste_clicks:.0f} clicks) — "
                     f"review and add negatives"),
            data={"campaign_id": cid, "total_cost": total_cost / 1e6,
                  "waste_cost": waste_cost / 1e6, "waste_share": share,
                  "waste_terms": waste_terms, "waste_clicks": waste_clicks},
            detected_at=_now(),
        ))
    return signals


# ── Detector: Vertical CPA Benchmark (external) ──
# Research: WordStream CPC/CVR by industry (config/vertical_benchmarks.yaml).
# Absolute-market complement to cross_account_outlier (peer-relative): flags
# accounts whose CPA is egregiously above the published benchmark for their
# vertical, seasonally adjusted. Coarse by construction — only fires on >3x.

def detect_vertical_cpa_benchmark(db: Database) -> list[Signal]:
    """Flag accounts whose CPA is far above their vertical's market benchmark.

    Benchmarks + params: config/vertical_benchmarks.yaml.
    """
    anchor = _data_anchor_date(db)
    if anchor is None:
        return []
    p = _bench.detector_params()
    window = int(p.get("window_days", 30))
    min_conv = float(p.get("min_conversions", 30))
    min_cost = int(p.get("min_cost_micros", 3000000000))
    high_mult = float(p.get("high_multiple", 3.0))
    month = int(anchor[5:7])  # seasonal index keyed by the data's month, per vertical

    rows = db.fetchall(windowed(f"""
        SELECT ap.account_id, ap.cpa, ap.conv, COALESCE(a.vertical, '') as vertical
        FROM (
            SELECT account_id,
                   sum(cost_micros) / NULLIF(sum(conversions), 0) / 1000000.0 as cpa,
                   sum(conversions) as conv
            FROM daily_metrics
            WHERE date >= current_date - {window}
            GROUP BY account_id
            HAVING sum(conversions) > {min_conv} AND sum(cost_micros) > {min_cost}
        ) ap
        LEFT JOIN accounts a ON a.account_id = ap.account_id
        WHERE ap.cpa IS NOT NULL AND ap.cpa > 0
    """, anchor))

    signals = []
    for acct, cpa, conv, vertical in rows:
        base = _bench.benchmark_cpa(vertical)
        if base is None:           # vertical not benchmarked (or unknown) -> skip
            continue
        season = _bench.seasonal_cpa_index(vertical, month)  # per-vertical monthly index
        expected = base * season
        if cpa <= high_mult * expected:
            continue
        ratio = cpa / expected if expected else 0
        signals.append(Signal(
            signal_id=_id(), account_id=acct,
            domain=PatternDomain.BIDDING_STRATEGY,
            signal_type="vertical_cpa_benchmark", severity=Severity.WARNING,
            value=cpa, threshold=high_mult * expected,
            message=(f"CPA ${cpa:,.0f} is {ratio:.1f}x the {vertical} industry benchmark "
                     f"(${expected:,.0f}, {season:.2f}x seasonal index for the month) "
                     f"— expensive for the vertical"),
            data={"cpa": cpa, "vertical": vertical, "benchmark_cpa": base,
                  "seasonal_index": season, "month": month, "expected_cpa": expected,
                  "ratio": ratio, "conv": conv},
            detected_at=_now(),
        ))
    return signals
