"""Verification C9 — cumulative system health score. One number for trust."""

from __future__ import annotations

from brightmatter.storage.database import Database
from brightmatter.verification.ledger import verify_ledger_integrity
from brightmatter.verification.integrity import verify_checksums
from brightmatter.verification.versions import reproducibility_test
from brightmatter.verification import events as ev

BASELINE_DECISIVE_ACC = 0.67   # Phase 5 backtest baseline


def _current_decisive_acc(db: Database) -> float:
    from brightmatter.patterns import operate
    r = operate.recommendation_accuracy(db, 14)
    return r.get("decisive_recommendation_accuracy", 0.0) if r.get("n") else 0.0


def compute_system_health(db: Database) -> dict:
    ledger = verify_ledger_integrity(db)
    checks_data = verify_checksums(db)
    repro = reproducibility_test(db)
    drift = ev.count_unresolved(db, "drift_alert")
    recent = ev.count_recent(db, 7)
    acc = _current_decisive_acc(db)
    acc_delta = acc - BASELINE_DECISIVE_ACC

    score = 100
    deductions = []
    if not ledger["ok"]:
        score -= 40; deductions.append(("ledger chain broken", -40))
    if not checks_data["ok"]:
        score -= 30; deductions.append((f"data checksum mismatches ({checks_data['mismatches']})", -30))
    if not repro["ok"]:
        score -= 20; deductions.append((f"template reproducibility fail ({len(repro['mismatches'])})", -20))
    if drift > 3:
        score -= 10; deductions.append((f"{drift} active drift alerts", -10))
    if recent > 5:
        score -= 10; deductions.append((f"{recent} anomalies in last 7d", -10))
    if acc_delta < -0.10:
        score -= 15; deductions.append((f"accuracy {acc_delta*100:.0f}pp below baseline", -15))
    elif acc_delta < -0.05:
        score -= 5; deductions.append((f"accuracy {acc_delta*100:.0f}pp below baseline", -5))

    score = max(0, score)
    return {
        "health_score": score,
        "status": "healthy" if score >= 80 else "degraded" if score >= 50 else "critical",
        "deductions": deductions,
        "checks": {
            "ledger": ledger, "data_checksums": checks_data, "reproducibility": repro,
            "active_drift_alerts": drift, "recent_anomalies": recent,
            "decisive_accuracy": round(acc, 3), "accuracy_vs_baseline_pp": round(acc_delta * 100, 1),
        },
    }


def render_trust_block(h: dict) -> str:
    c = h["checks"]
    lines = [f"## System Trust", f"Health: {h['health_score']}/100 ({h['status']})"]
    tick = lambda ok: "✓" if ok else "⚠"
    lines.append(f"{tick(c['ledger']['ok'])} Prediction ledger: {c['ledger']['n']} entries, "
                 + ("chain intact" if c['ledger']['ok'] else f"BROKEN at seq {c['ledger']['break_at']}"))
    lines.append(f"{tick(c['data_checksums']['ok'])} Data checksums: {c['data_checksums']['dates_verified']} "
                 f"dates, {c['data_checksums']['mismatches']} mismatches")
    lines.append(f"{tick(c['reproducibility']['ok'])} Template reproducibility: "
                 f"{c['reproducibility']['checked']} checked, {len(c['reproducibility']['mismatches'])} mismatch")
    lines.append(f"{tick(c['accuracy_vs_baseline_pp'] >= -5)} Accuracy vs baseline: "
                 f"{c['accuracy_vs_baseline_pp']:+.1f}pp")
    lines.append(f"{tick(c['active_drift_alerts'] <= 3)} Drift alerts: {c['active_drift_alerts']} active")
    for d, pts in h["deductions"]:
        lines.append(f"   −{abs(pts)}: {d}")
    return "\n".join(lines)
