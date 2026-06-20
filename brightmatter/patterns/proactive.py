"""Phase 7 — Proactive Recommendation Engine.

Scans every campaign with a known state, matches it against the magnitude-aware
template library (Phase 6.75-fix), and surfaces three outputs WITHOUT waiting for a
change to react to:

  pattern-backed recommendations — favorable templates match this state (act)
  inverse warnings               — unfavorable templates match this state (avoid)
  experimental hypotheses        — action categories with no template here but
                                   evidence in a broader profile (test to learn)

Ranking: warnings first (preventing harm > pursuing gain), then recommendations by
evidence strength, then experiments by how many campaigns the test would inform.
Classification uses the template's CPA median (favorable = CPA improves >=10%).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import magnitude as M

FAVORABLE_CPA = -0.10     # CPA median <= -10% -> favorable
UNFAVORABLE_CPA = 0.10    # CPA median >= +10% -> warning


def _load_mag_templates(db: Database) -> dict:
    """mag template_id -> {cond, cpa_median, n, metrics:{metric:(median,lo,hi,mae)}}."""
    rows = db.fetchall("""SELECT template_id, metric, median_delta, iqr_low, iqr_high, mae, n
                          FROM per_metric_predictions WHERE template_id LIKE 'mag:%'""")
    tmpl: dict[str, dict] = defaultdict(lambda: {"metrics": {}, "n": 0})
    for tid, metric, md, lo, hi, mae, n in rows:
        t = tmpl[tid]
        t["metrics"][metric] = {"median": md, "lo": lo, "hi": hi, "mae": mae}
        t["n"] = max(t["n"], n)
        if metric == "cpa":
            t["cpa_median"] = md
    return tmpl


def _parse_mag_id(tid: str) -> dict:
    """mag:budget__mag=medium_increase__single__ecommerce__apparel__25k-100k__performing_well"""
    body = tid[len("mag:"):]
    parts = body.split("__")
    cond = {"change_category": parts[0],
            "magnitude_bucket": parts[1].replace("mag=", ""),
            "is_multi_action": parts[2] == "multi"}
    rest = parts[3:]
    # last token is always pre_state; the segment tokens in between vary by level
    cond["pre_state"] = rest[-1]
    seg = rest[:-1]
    # map remaining tokens positionally to business_type/vertical/spend_tier as present
    keys = ["business_type", "vertical", "spend_tier"][:len(seg)]
    for k, v in zip(keys, seg):
        cond[k] = v
    return cond


def _campaign_states(db: Database) -> dict:
    """(account,campaign) -> dict(state, business_type, vertical, spend_tier) from the
    most recent episode + account profile."""
    rows = db.fetchall("""
        SELECT e.account_id, e.campaign_id, e.pre_state,
               COALESCE(NULLIF(a.business_type,''),'unknown'),
               COALESCE(NULLIF(a.vertical,''),'unknown'),
               COALESCE(NULLIF(a.spend_tier,''),'unknown'),
               e.recorded_at
        FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id
        WHERE e.campaign_id<>'' AND e.pre_state IS NOT NULL AND e.pre_state<>''
        ORDER BY e.recorded_at""")
    out = {}
    for acct, camp, state, biz, vert, tier, _ in rows:   # later rows overwrite -> most recent
        out[(acct, camp)] = {"state": state, "business_type": biz, "vertical": vert, "spend_tier": tier}
    return out


def _match(tmpl_by_cond: dict, cond_full: dict, category: str, mag: str, is_multi: bool):
    """Sharpest magnitude-aware template matching this campaign profile for a given
    (category, magnitude, is_multi). Mirrors the extraction cascade."""
    for keys in M._MAG_LEVELS:
        cond = {}
        ok = True
        for k in keys:
            if k == "change_category": cond[k] = category
            elif k == "magnitude_bucket": cond[k] = mag
            elif k == "is_multi_action": cond[k] = is_multi
            else: cond[k] = cond_full.get(k)
        tid = "mag:" + M._mag_id(cond)
        if tid in tmpl_by_cond:
            return tid
    return None


def proactive_scan(db: Database) -> dict:
    tmpl = _load_mag_templates(db)
    tmpl_ids = set(tmpl.keys())
    # categories + magnitudes present in the library
    lib = [_parse_mag_id(t) for t in tmpl_ids]
    categories = sorted({c["change_category"] for c in lib})
    mags_by_cat = defaultdict(set)
    for c in lib:
        mags_by_cat[c["change_category"]].add(c["magnitude_bucket"])
    # which (category) have ANY template (for gap detection by broader profile)
    states = _campaign_states(db)

    recommendations, warnings, experiments = [], [], []
    # precompute gap leverage: count campaigns sharing (state) lacking a category
    for (acct, camp), prof in states.items():
        cond_full = {"business_type": prof["business_type"], "vertical": prof["vertical"],
                     "spend_tier": prof["spend_tier"], "pre_state": prof["state"]}
        matched_cats = set()
        for cat in categories:
            for mag in sorted(mags_by_cat[cat]):
                for is_multi in (False, True):
                    tid = _match(tmpl, cond_full, cat, mag, is_multi)
                    if not tid:
                        continue
                    matched_cats.add(cat)
                    t = tmpl[tid]
                    cpa = t.get("cpa_median")
                    if cpa is None:
                        continue
                    metrics = {m: (v["median"], v["lo"], v["hi"], v["mae"]) for m, v in t["metrics"].items()}
                    rec = {"account_id": acct, "campaign_id": camp, "state": prof["state"],
                           "action": cat, "magnitude": mag, "multi": is_multi,
                           "cpa_median": cpa, "n": t["n"], "template_id": tid, "metrics": metrics}
                    if cpa <= FAVORABLE_CPA:
                        recommendations.append(rec)
                    elif cpa >= UNFAVORABLE_CPA:
                        warnings.append(rec)
        # knowledge gaps: a category with templates somewhere, but none matched this profile
        for cat in categories:
            if cat in matched_cats:
                continue
            # is there a broader-profile template (same state, any segment)?
            broader = [c for c in lib if c["change_category"] == cat and c["pre_state"] == prof["state"]]
            if broader:
                experiments.append({"account_id": acct, "campaign_id": camp, "state": prof["state"],
                                    "proposed_action": cat,
                                    "suggested_magnitude": Counter(c["magnitude_bucket"] for c in broader).most_common(1)[0][0],
                                    "rationale": f"Templates exist for {cat} in {prof['state']} elsewhere, "
                                                 f"but none for {prof['vertical']}/{prof['spend_tier']}. Test confirms transfer."})

    # rank: warnings by |cpa| & evidence; recs by favorable cpa & evidence; experiments by leverage
    warnings.sort(key=lambda r: (-r["cpa_median"], -r["n"]))
    recommendations.sort(key=lambda r: (r["cpa_median"], -r["n"]))
    gap_leverage = Counter((e["state"], e["proposed_action"]) for e in experiments)
    for e in experiments:
        e["campaigns_in_gap"] = gap_leverage[(e["state"], e["proposed_action"])]
    experiments.sort(key=lambda e: -e["campaigns_in_gap"])
    # dedupe experiments to one row per (state, action) for the report
    seen = set(); uniq_exp = []
    for e in experiments:
        k = (e["state"], e["proposed_action"])
        if k in seen:
            continue
        seen.add(k); uniq_exp.append(e)

    return {"campaigns_scanned": len(states),
            "recommendations": recommendations, "warnings": warnings,
            "experiments": uniq_exp}


def write_proactive_doc(db: Database, path: str, scan: dict) -> None:
    as_of = db.fetchone("SELECT max(date) FROM daily_metrics")[0]
    n = scan["campaigns_scanned"]
    recs, warns, exps = scan["recommendations"], scan["warnings"], scan["experiments"]
    camps_with_rec = len({(r["account_id"], r["campaign_id"]) for r in recs})
    camps_with_warn = len({(r["account_id"], r["campaign_id"]) for r in warns})

    def mline(r):
        ms = r["metrics"]
        parts = []
        for k in ("cost", "conversions", "cpa", "roas"):
            if k in ms:
                md = ms[k][0]; parts.append(f"{k} {md*100:+.0f}%")
        return ", ".join(parts)

    L = [f"# BrightMatter Proactive Recommendations — {as_of}", "",
         "*Auto-generated. Magnitude-aware templates; no LLM in the loop.*", "",
         "## Coverage",
         f"- Campaigns scanned (state known): **{n}**",
         f"- With >=1 recommendation: {camps_with_rec} · with >=1 warning: {camps_with_warn} · "
         f"experiments proposed: {len(exps)}", "",
         "## Top warnings (inverse — do NOT do this)", ""]
    for w in warns[:10]:
        L.append(f"- **avoid {w['magnitude']} {w['action']}** on {w['campaign_id']} "
                 f"({w['state']}) → predicted {mline(w)} · n={w['n']}")
    L += ["", "## Top pattern-backed recommendations", ""]
    for r in recs[:10]:
        L.append(f"- **{r['magnitude']} {r['action']}** on {r['campaign_id']} "
                 f"({r['state']}) → predicted {mline(r)} · n={r['n']}")
    L += ["", "## Experiments proposed (fill knowledge gaps)", ""]
    for e in exps[:10]:
        L.append(f"- test **{e['suggested_magnitude']} {e['proposed_action']}** in {e['state']} "
                 f"({e['campaigns_in_gap']} campaigns would benefit) — {e['rationale']}")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
