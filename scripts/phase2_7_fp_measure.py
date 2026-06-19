"""Phase 2.7 — rigorous false-positive measurement for the volatility-widened
cpa_spike threshold.

The Phase 2 lock-in item "FP rate measurably lower than Phase 1" was unproven:
volatility widens cpa_spike's threshold (×1.5 on high-CPA-volatility campaigns)
but nobody measured whether the spikes it *removes* are actually false alarms.

Method (a clean before/after):
  • FLAT set     = campaigns flagged by cpa_spike with the volatility multiplier
                   forced to 1.0 (the Phase-1 behaviour).
  • WIDENED set  = campaigns flagged with the production multiplier
                   (× COALESCE(threshold_multiplier, 1.0)).
  • SUPPRESSED   = FLAT − WIDENED  (spikes the widening removed).
  • KEPT         = WIDENED         (spikes that survive).
Audit BOTH sets with the cpa_spike disconfirmation harness (T1 recent volume,
T2 single-day outlier, T3 strategy stability, T4 AOV lift). A campaign with >=1
disconfirming test is a likely false positive. If SUPPRESSED has a materially
higher FP rate than KEPT, the widening is removing noise, not signal — the claim
holds.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.analysis.change_detectors import _data_anchor_date, windowed
from brightmatter.thresholds import effective_thresholds
from brightmatter.validation.cpa_spike import (
    test_recent_volume, test_single_day_outlier,
    test_bidding_strategy_stability, test_conversion_value_movement,
)

db = Database(); db.initialize()
th = effective_thresholds("cpa_spike")
anchor = _data_anchor_date(db)
mult = float(th["recent_cpa_multiplier"])


def flagged(use_volatility: bool) -> set[tuple[str, str]]:
    """Return {(account_id, campaign_id)} flagged by cpa_spike, with or without
    the volatility threshold multiplier."""
    vol_term = "* COALESCE(ct.threshold_multiplier, 1.0)" if use_volatility else ""
    rows = db.fetchall(windowed(f"""
        WITH recent AS (
            SELECT account_id, campaign_id,
                   sum(cost_micros) / NULLIF(sum(conversions), 0) as recent_cpa
            FROM daily_metrics
            WHERE date >= current_date - {int(th['recent_window_days'])}
            GROUP BY account_id, campaign_id
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
        SELECT r.account_id, r.campaign_id
        FROM recent r
        JOIN baseline b ON r.account_id = b.account_id AND r.campaign_id = b.campaign_id
        LEFT JOIN campaign_trends ct ON ct.account_id = r.account_id
              AND ct.campaign_id = r.campaign_id AND ct.metric = 'cpa' AND ct.window_days = 30
        WHERE r.recent_cpa > b.baseline_cpa * {mult} {vol_term}
    """, anchor))
    return {(r[0], r[1]) for r in rows}


def audit(pairs: set[tuple[str, str]]) -> dict:
    """Run the 4 harness tests on each campaign; count likely false positives
    (>=1 disconfirm) and total disconfirming tests."""
    fp = 0
    disconfirm_tests = 0
    total_tests = 0
    per_test_disconfirm = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for acct, camp in pairs:
        results = [
            test_recent_volume(db, acct, camp),
            test_single_day_outlier(db, acct, camp),
            test_bidding_strategy_stability(db, acct, camp),
            test_conversion_value_movement(db, acct, camp, {}),
        ]
        d = [r for r in results if r.verdict == "disconfirm"]
        if d:
            fp += 1
        disconfirm_tests += len(d)
        total_tests += len(results)
        for r in d:
            per_test_disconfirm[r.test_id] = per_test_disconfirm.get(r.test_id, 0) + 1
    n = len(pairs)
    return {
        "n": n,
        "fp": fp,
        "fp_rate": (fp / n) if n else 0.0,
        "disconfirm_tests": disconfirm_tests,
        "total_tests": total_tests,
        "per_test_disconfirm": per_test_disconfirm,
    }


flat = flagged(use_volatility=False)
widened = flagged(use_volatility=True)
suppressed = flat - widened
kept = widened

print(f"\n[2.7] cpa_spike flagged — FLAT (×1.0): {len(flat)} | "
      f"WIDENED (production): {len(widened)} | SUPPRESSED by widening: {len(suppressed)}")

a_supp = audit(suppressed)
a_kept = audit(kept)
a_flat = audit(flat)

def show(label, a):
    print(f"\n[2.7] {label}: n={a['n']}")
    if a["n"] == 0:
        return
    print(f"[2.7]   likely false positives (>=1 disconfirm): {a['fp']} "
          f"({a['fp_rate']*100:.0f}%)")
    print(f"[2.7]   disconfirming tests: {a['disconfirm_tests']}/{a['total_tests']} "
          f"({a['disconfirm_tests']/a['total_tests']*100:.0f}%)")
    print(f"[2.7]   by test: {a['per_test_disconfirm']}")

show("FLAT (all Phase-1 spikes)", a_flat)
show("KEPT (survive widening)", a_kept)
show("SUPPRESSED (removed by widening)", a_supp)

print("\n[2.7] === VERDICT ===")
if a_supp["n"] == 0:
    print("[2.7] No spikes were suppressed — volatility multiplier changed nothing on this panel.")
else:
    lift = a_supp["fp_rate"] - a_kept["fp_rate"]
    print(f"[2.7] FP rate — suppressed {a_supp['fp_rate']*100:.0f}% vs kept "
          f"{a_kept['fp_rate']*100:.0f}%  (Δ {lift*100:+.0f}pp)")
    if a_supp["fp_rate"] > a_kept["fp_rate"]:
        print("[2.7] Widening removes a HIGHER-FP slice than it keeps → it cuts noise, not signal. CLAIM SUPPORTED.")
    else:
        print("[2.7] Suppressed slice is NOT more FP-prone than kept → widening may be discarding real spikes. CLAIM NOT SUPPORTED.")
db.close()
