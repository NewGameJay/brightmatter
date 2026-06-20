"""Phase 4.75 — segment detectors + episode-attribute features.

Computes per-campaign segment features from the window-aggregated `campaign_segments`
and `ad_strength` tables, emits five detector signals, and exposes bucketed
categorical attributes for exception mining (4.5.2 re-run).

Five detectors:
  device_mobile_drag    — heavy mobile traffic with a large mobile CVR deficit
  search_partners_waste — material Search-Partners spend at a worse CPA than Search
  dead_zone             — hours/days with real spend but ~zero conversions
  geo_cpa_outlier       — CPA varies wildly across geos (serving very different markets)
  weak_ad_strength      — most RSAs are POOR/AVERAGE (creative quality ceiling)
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from brightmatter.models.patterns import PatternDomain, Severity, Signal
from brightmatter.storage.database import Database
import uuid
from datetime import datetime, timezone


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── feature computation ──

def compute_campaign_segment_features(db: Database) -> dict[tuple, dict]:
    """(account,campaign) -> feature dict from campaign_segments + ad_strength."""
    feats: dict[tuple, dict] = defaultdict(dict)

    rows = db.fetchall("""
        SELECT account_id, campaign_id, dimension, segment_value,
               impressions, clicks, cost_micros, conversions
        FROM campaign_segments
    """)
    grp: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    for acct, camp, dim, val, imp, clk, cost, conv in rows:
        grp[(acct, camp)][dim].append((val, imp, clk, cost / 1e6, conv))

    for key, dims in grp.items():
        f = {}
        # device: mobile traffic share + CVR gap (mobile vs non-mobile)
        dev = dims.get("device", [])
        if dev:
            tot_clk = sum(d[2] for d in dev) or 1
            mob = [d for d in dev if d[0] == "MOBILE"]
            non = [d for d in dev if d[0] != "MOBILE"]
            f["mobile_traffic_share"] = sum(d[2] for d in mob) / tot_clk
            mob_cvr = (sum(d[4] for d in mob) / sum(d[2] for d in mob)) if sum(d[2] for d in mob) else 0
            non_cvr = (sum(d[4] for d in non) / sum(d[2] for d in non)) if sum(d[2] for d in non) else 0
            f["mobile_cvr_gap"] = (non_cvr / mob_cvr) if mob_cvr > 0 else None
        # network: Search-Partners spend share + CPA ratio vs Search
        net = dims.get("network", [])
        if net:
            tot_cost = sum(d[3] for d in net) or 1
            part = [d for d in net if "PARTNER" in d[0]]
            srch = [d for d in net if d[0] in ("SEARCH", "GOOGLE_SEARCH")]
            f["search_partners_spend_share"] = sum(d[3] for d in part) / tot_cost
            p_cpa = (sum(d[3] for d in part) / sum(d[4] for d in part)) if sum(d[4] for d in part) else None
            s_cpa = (sum(d[3] for d in srch) / sum(d[4] for d in srch)) if sum(d[4] for d in srch) else None
            f["partners_cpa_ratio"] = (p_cpa / s_cpa) if (p_cpa and s_cpa) else None
        # hour + dow dead zones: a bucket with >=5% of spend but zero conversions
        for dim in ("hour", "dow"):
            seg = dims.get(dim, [])
            if seg:
                tot = sum(d[3] for d in seg) or 1
                dead = [d for d in seg if d[3] / tot >= 0.05 and d[4] == 0]
                f[f"{dim}_dead_zone_spend_share"] = sum(d[3] for d in dead) / tot
        f["has_dead_zones"] = bool(f.get("hour_dead_zone_spend_share", 0) > 0.10
                                   or f.get("dow_dead_zone_spend_share", 0) > 0.10)
        # geo CPA variance (spend-weighted CV across geos with conversions)
        geo = [d for d in dims.get("geo", []) if d[4] > 0 and d[3] > 0]
        if len(geo) >= 3:
            cpas = [d[3] / d[4] for d in geo]
            m = statistics.mean(cpas)
            f["geo_cpa_variance"] = (statistics.pstdev(cpas) / m) if m > 0 else 0.0
        feats[key] = f

    # ad strength distribution (RSAs)
    strength = db.fetchall("""
        SELECT account_id, campaign_id, ad_strength, count(*) FROM ad_strength GROUP BY 1,2,3
    """)
    sgrp: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    for acct, camp, st, c in strength:
        sgrp[(acct, camp)][st] += c
    for key, dist in sgrp.items():
        total = sum(dist.values()) or 1
        weak = dist.get("POOR", 0) + dist.get("AVERAGE", 0)
        feats[key]["poor_ad_share"] = weak / total
        feats[key]["excellent_ad_share"] = dist.get("EXCELLENT", 0) / total
        feats[key]["n_rsa"] = total
    return dict(feats)


# ── bucketed categorical attributes for exception mining ──

def episode_segment_attributes(feats: dict) -> dict:
    """Map a campaign's feature dict to categorical buckets usable as exception dims."""
    def b(cond, yes, no, na="unknown"):
        return na if cond is None else (yes if cond else no)
    return {
        "device_profile": b(feats.get("mobile_traffic_share"),
                            None, None) if "mobile_traffic_share" not in feats else
                          ("mobile_heavy" if feats["mobile_traffic_share"] > 0.5 else "desktop_heavy"),
        "mobile_cvr_drag": b((feats.get("mobile_cvr_gap") or 0) >= 1.5
                             if feats.get("mobile_cvr_gap") is not None else None,
                             "mobile_drag", "no_drag"),
        "partners_exposed": b("search_partners_spend_share" in feats,
                              "partners" if feats.get("search_partners_spend_share", 0) > 0.10 else "no_partners",
                              None) if "search_partners_spend_share" in feats else "unknown",
        "dead_zones": "dead_zones" if feats.get("has_dead_zones") else "no_dead_zones",
        "geo_variance": ("high_geo_var" if feats.get("geo_cpa_variance", 0) > 0.5 else "low_geo_var")
                        if "geo_cpa_variance" in feats else "unknown",
        "ad_quality": ("weak_ads" if feats.get("poor_ad_share", 0) > 0.5 else "ok_ads")
                      if "n_rsa" in feats else "unknown",
    }


# ── five detectors (emit signals) ──

def detect_segment_signals(db: Database) -> list[Signal]:
    feats = compute_campaign_segment_features(db)
    names = dict(((r[0], r[1]), r[2]) for r in db.fetchall(
        "SELECT DISTINCT account_id, campaign_id, campaign_name FROM daily_metrics"))
    out = []
    for (acct, camp), f in feats.items():
        nm = names.get((acct, camp), camp)
        # 1. mobile drag
        if f.get("mobile_traffic_share", 0) > 0.6 and (f.get("mobile_cvr_gap") or 0) >= 2.0:
            out.append(Signal(signal_id=_id(), account_id=acct, campaign_id=camp,
                domain=PatternDomain.BIDDING_STRATEGY, signal_type="device_mobile_drag",
                severity=Severity.WARNING, value=f["mobile_cvr_gap"], threshold=2.0,
                message=f"Campaign '{nm}' is {f['mobile_traffic_share']*100:.0f}% mobile with "
                        f"{f['mobile_cvr_gap']:.1f}x worse mobile CVR — budget mostly reaches low-converting mobile.",
                data={"campaign_id": camp, **{k: f[k] for k in ("mobile_traffic_share", "mobile_cvr_gap")}},
                detected_at=_now()))
        # 2. search partners waste
        if f.get("search_partners_spend_share", 0) > 0.15 and (f.get("partners_cpa_ratio") or 0) >= 1.5:
            out.append(Signal(signal_id=_id(), account_id=acct, campaign_id=camp,
                domain=PatternDomain.BIDDING_STRATEGY, signal_type="search_partners_waste",
                severity=Severity.WARNING, value=f["partners_cpa_ratio"], threshold=1.5,
                message=f"Campaign '{nm}' spends {f['search_partners_spend_share']*100:.0f}% on Search Partners "
                        f"at {f['partners_cpa_ratio']:.1f}x the Search CPA.",
                data={"campaign_id": camp}, detected_at=_now()))
        # 3. dead zones
        if f.get("has_dead_zones"):
            share = max(f.get("hour_dead_zone_spend_share", 0), f.get("dow_dead_zone_spend_share", 0))
            out.append(Signal(signal_id=_id(), account_id=acct, campaign_id=camp,
                domain=PatternDomain.BIDDING_STRATEGY, signal_type="dead_zone_spend",
                severity=Severity.INFO, value=share, threshold=0.10,
                message=f"Campaign '{nm}' spends {share*100:.0f}% in hours/days with ~zero conversions.",
                data={"campaign_id": camp}, detected_at=_now()))
        # 4. geo outlier
        if f.get("geo_cpa_variance", 0) > 1.0:
            out.append(Signal(signal_id=_id(), account_id=acct, campaign_id=camp,
                domain=PatternDomain.BIDDING_STRATEGY, signal_type="geo_cpa_outlier",
                severity=Severity.INFO, value=f["geo_cpa_variance"], threshold=1.0,
                message=f"Campaign '{nm}' CPA varies {f['geo_cpa_variance']:.1f}x (CV) across geos.",
                data={"campaign_id": camp}, detected_at=_now()))
        # 5. weak ad strength
        if f.get("n_rsa", 0) >= 3 and f.get("poor_ad_share", 0) > 0.5:
            out.append(Signal(signal_id=_id(), account_id=acct, campaign_id=camp,
                domain=PatternDomain.CREATIVE, signal_type="weak_ad_strength",
                severity=Severity.WARNING, value=f["poor_ad_share"], threshold=0.5,
                message=f"Campaign '{nm}': {f['poor_ad_share']*100:.0f}% of RSAs are Poor/Average ad strength.",
                data={"campaign_id": camp}, detected_at=_now()))
    return out
