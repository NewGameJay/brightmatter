"""GA4 x Google Ads cross-platform confidence upgrades (research causal chains 1 & 2).

Joins Google Ads signals to GA4 landing-page evidence via the campaign's final-URL
path (campaign_final_urls.norm_path == ga4_landing_pages.landing_page, same account).
Where GA4 corroborates, upgrades the Ads signal's confidence tier and records the link.

  Chain 2 (mobile UX): device_mobile_drag (Ads) + GA4 mobile engagement gap on the
    campaign's page -> CONFIRMED.
  Chain 1 (landing page): cvr_drop/cvr_change/cpa_spike/cpa_change (Ads) + GA4 weak
    engagement (low, or a recent drop) on the campaign's page -> upgrade toward CONFIRMED.

Excludes GA4 '(not set)'/'(other)' buckets (high-cardinality overflow on big
properties — unjoinable). The "why" then comes from squirrelscan on matched_page.
"""

from __future__ import annotations

from collections import defaultdict

from brightmatter.storage.database import Database

LOW_ENGAGEMENT = 0.40        # paid LP below 40% engagement = poor (benchmarks)
ENG_DROP_PP = 0.15
MOBILE_GAP_PP = 0.25
ADS_SIGNALS = ("cvr_drop", "cvr_change", "cpa_spike", "cpa_change", "device_mobile_drag")
_TIER_RANK = {"": 0, "SUGGESTIVE": 1, "LIKELY": 2, "CONFIRMED": 3}


def _page_evidence(db: Database) -> dict:
    """(account, path) -> evidence dict for joinable GA4 pages (real pages only)."""
    anchor = db.fetchone("SELECT max(date) FROM ga4_landing_pages")[0]
    rows = db.fetchall(f"""
        WITH base AS (
            SELECT account_id, landing_page, device,
                   CASE WHEN date > DATE '{anchor}' - 7 THEN 'recent' ELSE 'base' END w,
                   sum(sessions) s, sum(engaged_sessions) es
            FROM ga4_landing_pages
            WHERE landing_page NOT IN ('(not set)','(other)','')
              AND date > DATE '{anchor}' - 28
            GROUP BY 1,2,3,4
        )
        SELECT account_id, landing_page,
               sum(s) sess,
               sum(es)*1.0/NULLIF(sum(s),0) eng,
               sum(CASE WHEN device='mobile' THEN es END)*1.0/NULLIF(sum(CASE WHEN device='mobile' THEN s END),0) mob_eng,
               sum(CASE WHEN device='desktop' THEN es END)*1.0/NULLIF(sum(CASE WHEN device='desktop' THEN s END),0) desk_eng,
               sum(CASE WHEN w='recent' THEN es END)*1.0/NULLIF(sum(CASE WHEN w='recent' THEN s END),0) r_eng,
               sum(CASE WHEN w='base' THEN es END)*1.0/NULLIF(sum(CASE WHEN w='base' THEN s END),0) b_eng
        FROM base GROUP BY 1,2
    """)
    ev = {}
    for acct, page, sess, eng, mob, desk, r_eng, b_eng in rows:
        ev[(acct, page)] = {"sessions": sess, "eng": eng, "mob": mob, "desk": desk,
                            "r_eng": r_eng, "b_eng": b_eng}
    return ev


def _campaign_paths(db: Database) -> dict:
    """(account, campaign_id) -> set of GA4-joinable norm_paths."""
    out = defaultdict(set)
    for acct, cid, path in db.fetchall(
            "SELECT account_id, campaign_id, norm_path FROM campaign_final_urls WHERE norm_path IS NOT NULL"):
        out[(acct, cid)].add(path)
    return out


def run_crossref(db: Database) -> dict:
    matched = {r[0] for r in db.fetchall("SELECT account_id FROM ga4_property_map WHERE match_confidence='high'")}
    evidence = _page_evidence(db)
    cpaths = _campaign_paths(db)

    sig_in = ",".join(f"'{s}'" for s in ADS_SIGNALS)
    sigs = db.fetchall(f"""
        SELECT signal_id, account_id, campaign_id, signal_type, COALESCE(confidence_tier,'')
        FROM signals WHERE signal_type IN ({sig_in})""")
    db.execute("DELETE FROM cross_platform_links")
    summary = {"examined": 0, "joinable": 0, "upgraded": 0,
               "by_chain": defaultdict(int), "by_type": defaultdict(int)}
    for sid, acct, cid, stype, tier in sigs:
        if acct not in matched or not cid:
            continue
        summary["examined"] += 1
        paths = cpaths.get((acct, cid), set())
        # find the campaign's pages that have GA4 evidence
        pages = [(p, evidence[(acct, p)]) for p in paths if (acct, p) in evidence]
        if not pages:
            continue
        summary["joinable"] += 1
        # pick the highest-traffic matched page as the representative
        page, e = max(pages, key=lambda x: x[1]["sessions"] or 0)
        chain = note = new_tier = None
        if stype == "device_mobile_drag":
            if e["mob"] is not None and e["desk"] is not None and (e["desk"] - e["mob"]) >= MOBILE_GAP_PP:
                chain = "chain_2_mobile_ux"; new_tier = "CONFIRMED"
                note = f"GA4: mobile engagement {e['mob']*100:.0f}% vs desktop {e['desk']*100:.0f}% on {page}"
        else:  # cvr/cpa signals -> landing-page chain
            drop = (e["b_eng"] - e["r_eng"]) if (e["b_eng"] and e["r_eng"] is not None) else 0
            if e["eng"] is not None and e["eng"] < LOW_ENGAGEMENT:
                chain = "chain_1_landing_page"; new_tier = "CONFIRMED"
                note = f"GA4: landing page {page} engagement only {e['eng']*100:.0f}% (paid LP weak)"
            elif drop >= ENG_DROP_PP:
                chain = "chain_1_landing_page"; new_tier = "CONFIRMED"
                note = f"GA4: engagement on {page} fell {drop*100:.0f}pp recently"
        if not chain:
            continue
        upgraded = _TIER_RANK.get(new_tier, 0) > _TIER_RANK.get(tier, 0)
        db.execute("""INSERT OR REPLACE INTO cross_platform_links
            (signal_id, account_id, campaign_id, signal_type, matched_page, chain,
             ga4_evidence, old_tier, new_tier) VALUES (?,?,?,?,?,?,?,?,?)""",
            [sid, acct, cid, stype, page, chain, note, tier, new_tier])
        if upgraded:
            db.execute("""UPDATE signals SET confidence_tier=?,
                          what_we_know = what_we_know || ' [GA4 cross-ref] ' || ?
                          WHERE signal_id=?""", [new_tier, note, sid])
            summary["upgraded"] += 1
            summary["by_chain"][chain] += 1
            summary["by_type"][stype] += 1
    db.execute("CHECKPOINT")
    summary["by_chain"] = dict(summary["by_chain"]); summary["by_type"] = dict(summary["by_type"])
    return summary
