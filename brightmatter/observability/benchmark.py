"""System scorecard — benchmark the full BrightMatter system from real tables.

One call rolls up every layer's health into a single structured object: coverage,
signal validation (harness verdicts), episode/template state, recommendation accuracy
(the product metric), per-metric calibration, and the GA4 cross-platform layer. This
is the quantitative companion to the per-episode pipeline trace.
"""

from __future__ import annotations

from collections import defaultdict

from brightmatter.storage.database import Database
from brightmatter.patterns import operate


def _scalar(db, sql, params=None):
    r = db.fetchone(sql, params or [])
    return r[0] if r else None


def system_scorecard(db: Database, run_harnesses: bool = False) -> dict:
    sc: dict = {}

    # ── coverage ──
    sc["coverage"] = {
        "accounts_with_metrics": _scalar(db, "SELECT count(DISTINCT account_id) FROM daily_metrics"),
        "campaigns": _scalar(db, "SELECT count(DISTINCT campaign_id) FROM daily_metrics"),
        "episodes": _scalar(db, "SELECT count(*) FROM episodes"),
        "ga4_accounts": _scalar(db, "SELECT count(DISTINCT account_id) FROM ga4_landing_pages"),
        "date_range": [str(x) for x in (db.fetchone("SELECT min(date), max(date) FROM daily_metrics") or (None, None))],
    }

    # ── stage 1: signals + validation ──
    sig_types = db.fetchall("SELECT signal_type, count(*) FROM signals GROUP BY 1 ORDER BY 2 DESC")
    sc["signals"] = {
        "total": _scalar(db, "SELECT count(*) FROM signals"),
        "by_tier": dict(db.fetchall("SELECT COALESCE(NULLIF(confidence_tier,''),'(none)'), count(*) FROM signals GROUP BY 1")),
        "by_severity": dict(db.fetchall("SELECT severity, count(*) FROM signals GROUP BY 1")),
        "top_types": dict(sig_types[:10]),
    }
    if run_harnesses:
        from brightmatter.validation import AUDITS
        verdicts = {}
        for name, fn in AUDITS.items():
            try:
                audits = fn(db)
                if not audits:
                    verdicts[name] = ("NO_SIGNALS", 0); continue
                fp = sum(1 for a in audits if a.overall == "likely_false_positive")
                rate = fp / len(audits)
                v = "KEEP" if rate == 0 else "MONITOR" if rate < 0.15 else "REVISE"
                verdicts[name] = (v, len(audits))
            except Exception as e:  # noqa: BLE001
                verdicts[name] = (f"ERR:{str(e)[:20]}", 0)
        sc["harness_verdicts"] = verdicts

    # ── stage 2: episodes ──
    sc["episodes"] = {
        "by_outcome": dict(db.fetchall("SELECT outcome, count(*) FROM episodes GROUP BY 1 ORDER BY 2 DESC")),
        "confounded_pct": round((_scalar(db, "SELECT count(*) FROM episodes WHERE outcome='confounded'") or 0)
                                / max(1, sc["coverage"]["episodes"]) * 100, 1),
        "by_state": dict(db.fetchall("SELECT COALESCE(NULLIF(pre_state,''),'(untagged)'), count(*) FROM episodes GROUP BY 1 ORDER BY 2 DESC")),
    }

    # ── stage 3: templates ──
    sc["templates"] = {
        "total": _scalar(db, "SELECT count(DISTINCT template_id) FROM templates"),
        "by_status": dict(db.fetchall("SELECT status, count(*) FROM templates GROUP BY 1")),
        "magnitude_aware": _scalar(db, "SELECT count(DISTINCT template_id) FROM per_metric_predictions WHERE template_id LIKE 'mag:%'"),
    }

    # ── stage 4: recommendations ──
    sc["recommendations"] = {
        "registered": _scalar(db, "SELECT count(*) FROM live_predictions"),
        "by_call": dict(db.fetchall("""
            SELECT lp.recommendation, count(*) FROM live_predictions lp GROUP BY 1""")) if _scalar(db, "SELECT count(*) FROM live_predictions") else {},
        "cross_platform_upgrades": _scalar(db, "SELECT count(*) FROM cross_platform_links WHERE new_tier='CONFIRMED'"),
    }

    # ── stage 6: accuracy (THE product metric) + calibration ──
    rec = operate.recommendation_accuracy(db, 14)
    sc["accuracy_14d"] = {
        "decisive_recommendation_accuracy": round(rec.get("decisive_recommendation_accuracy", 0), 3),
        "decisive_n": rec.get("decisive_n", 0),
        "abstention_rate": round(rec.get("abstention_rate", 0), 3),
        "direction_accuracy": round(rec.get("direction_accuracy", 0), 3),
        "by_recommendation": {k: {"n": v["n"], "acc": round(v["rec_acc"], 2)}
                              for k, v in rec.get("by_recommendation", {}).items()},
    } if rec.get("n") else {"n": 0}

    # per-metric calibration from the magnitude hypothesis loop
    mp = db.fetchall("""SELECT metric, count(*), avg(error),
                        avg(CASE WHEN within_iqr THEN 1.0 ELSE 0.0 END)
                        FROM metric_predictions WHERE resolved GROUP BY 1 ORDER BY 3""")
    sc["per_metric_calibration"] = {m: {"n": n, "mae_pp": round(mae * 100, 1), "within_iqr": round(wi, 2)}
                                    for m, n, mae, wi in mp}

    # ── GA4 layer ──
    sc["ga4"] = {
        "detector_signals": dict(db.fetchall("SELECT signal_type, count(*) FROM signals WHERE signal_type LIKE 'ga4_%' GROUP BY 1")),
        "page_audits": _scalar(db, "SELECT count(*) FROM ga4_page_audits"),
        "engagement_trends": dict(db.fetchall("SELECT classification, count(*) FROM ga4_page_trends GROUP BY 1")),
    }
    return sc


def print_scorecard(sc: dict) -> None:
    cov = sc["coverage"]
    print(f"\n{'='*64}\nBRIGHTMATTER SYSTEM SCORECARD\n{'='*64}")
    print(f"Coverage: {cov['accounts_with_metrics']} accounts · {cov['campaigns']} campaigns · "
          f"{cov['episodes']} episodes · {cov['ga4_accounts']} GA4 accounts · {cov['date_range'][0]}→{cov['date_range'][1]}")
    print(f"\n[1] SIGNALS: {sc['signals']['total']} | tiers {sc['signals']['by_tier']}")
    if "harness_verdicts" in sc:
        keep = sum(1 for v in sc["harness_verdicts"].values() if v[0] == "KEEP")
        mon = sum(1 for v in sc["harness_verdicts"].values() if v[0] == "MONITOR")
        rev = sum(1 for v in sc["harness_verdicts"].values() if v[0] == "REVISE")
        print(f"    harnesses: {keep} KEEP · {mon} MONITOR · {rev} REVISE (of {len(sc['harness_verdicts'])})")
    print(f"[2] EPISODES: {sc['episodes']['by_outcome']} | confounded {sc['episodes']['confounded_pct']}%")
    print(f"[3] TEMPLATES: {sc['templates']['total']} ({sc['templates']['by_status']}) | mag-aware {sc['templates']['magnitude_aware']}")
    print(f"[4] RECOMMENDATIONS: {sc['recommendations']['registered']} registered {sc['recommendations']['by_call']}")
    print(f"    cross-platform upgrades: {sc['recommendations']['cross_platform_upgrades']}")
    a = sc["accuracy_14d"]
    if a.get("decisive_n"):
        print(f"[6] ACCURACY (14d): decisive recommendation {a['decisive_recommendation_accuracy']*100:.0f}% "
              f"(n={a['decisive_n']}) · abstain {a['abstention_rate']*100:.0f}% · direction {a['direction_accuracy']*100:.0f}%")
        print(f"    by call: {a['by_recommendation']}")
    print(f"    per-metric MAE (pp): " + " ".join(f"{m}={d['mae_pp']:.0f}" for m, d in sc['per_metric_calibration'].items()))
    print(f"[GA4] detector signals {sc['ga4']['detector_signals']} | page audits {sc['ga4']['page_audits']} | "
          f"trends {sc['ga4']['engagement_trends']}")
    print("="*64)
