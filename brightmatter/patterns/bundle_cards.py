"""Bundle -> performance cards (Phase 1.75 Step 3).

The first 'what works' output: for each change category / bundle signature,
aggregate the CLEAN (attributable) episodes into an outcome card — distribution,
magnitude, account spread, vertical/tier breakdown, and a confidence level.

PRELIMINARY: built on Phase 1.5 episodes with NO trend adjustment (Phase 2).
Confounded episodes are excluded — they can't be attributed to one action.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from brightmatter.storage.database import Database

# Sample-size confidence (per the doc): directional at 10, reliable at 30.
RELIABLE_N = 30
DIRECTIONAL_N = 10


def _confidence(n: int, n_accounts: int) -> str:
    if n >= RELIABLE_N and n_accounts >= 8:
        return "RELIABLE"
    if n >= DIRECTIONAL_N and n_accounts >= 4:
        return "DIRECTIONAL"
    return "LOW"


def analyze_bundles(db: Database, min_episodes: int = DIRECTIONAL_N) -> list[dict[str, Any]]:
    """One card per change_category over CLEAN episodes (>= min_episodes)."""
    rows = db.fetchall("""
        SELECT e.change_category, e.actor, e.outcome, e.outcome_magnitude,
               e.account_id, COALESCE(NULLIF(a.vertical, ''), 'unknown') as vertical,
               COALESCE(NULLIF(a.spend_tier, ''), 'unknown') as tier
        FROM episodes e
        LEFT JOIN accounts a ON a.account_id = e.account_id
        WHERE e.outcome <> 'confounded'
    """)

    groups: dict[str, list[tuple]] = defaultdict(list)
    for cat, actor, outcome, mag, acct, vertical, tier in rows:
        groups[cat].append((actor, outcome, mag or 0.0, acct, vertical, tier))

    cards = []
    for cat, eps in groups.items():
        n = len(eps)
        if n < min_episodes:
            continue
        accounts = {e[3] for e in eps}
        oc = Counter(e[1] for e in eps)
        imp = [e[2] for e in eps if e[1] == "improved"]
        deg = [e[2] for e in eps if e[1] == "degraded"]

        def _seg(idx: int) -> dict[str, dict[str, Any]]:
            seg: dict[str, list] = defaultdict(list)
            for e in eps:
                seg[e[idx]].append(e[1])
            out = {}
            for k, outs in seg.items():
                m = len(outs)
                if m < 3:
                    continue
                out[k] = {"n": m, "improved_pct": sum(o == "improved" for o in outs) / m}
            return dict(sorted(out.items(), key=lambda kv: -kv[1]["n"]))

        cards.append({
            "category": cat,
            "actor": Counter(e[0] for e in eps).most_common(1)[0][0],
            "n": n,
            "accounts": len(accounts),
            "improved": oc["improved"], "degraded": oc["degraded"], "neutral": oc["neutral"],
            "avg_improve_mag": (sum(imp) / len(imp)) if imp else 0.0,
            "avg_degrade_mag": (sum(deg) / len(deg)) if deg else 0.0,
            "by_vertical": _seg(4),
            "by_tier": _seg(5),
            "confidence": _confidence(n, len(accounts)),
        })
    return sorted(cards, key=lambda c: -c["n"])
