#!/usr/bin/env python3
"""
Seed BrightMatter test Supabase from MH-OS signal data.

Reads:
  - mh-os/20_intelligence/signals/signal-log.jsonl  → events + episodic_memory
  - mh-os/20_intelligence/build-log/build-log.jsonl → events + episodic_memory
  - mh-os/research/artifacts/linkedin-assisted-deals.csv → events (outcome data)

Produces episodic_memory entries with realistic prediction/outcome pairs,
events for the shared bus, and a handful of semantic_patterns from aggregates.
"""

import csv
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from lib.supabase_client import get_supabase

MHOS_ROOT = "/Applications/MH1/mh-os"
TENANT_ID = "marketerhire"


def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_schema"):
                continue
            rows.append(obj)
    return rows


def seed_signals(db):
    """Seed events + episodic_memory from signal-log.jsonl."""
    path = os.path.join(MHOS_ROOT, "20_intelligence/signals/signal-log.jsonl")
    if not os.path.exists(path):
        print(f"  [SKIP] {path} not found")
        return 0, 0

    signals = load_jsonl(path)
    events = []
    episodes = []

    for i, sig in enumerate(signals):
        event_id = str(uuid.uuid4())
        source_task = sig.get("source", "unknown")
        lever = sig.get("lever", "All")
        metrics = sig.get("metrics", {})
        date_str = sig.get("date", "2026-03-01")

        events.append({
            "id": event_id,
            "source": "mh-os",
            "event_type": "signal",
            "skill_name": source_task,
            "client_id": TENANT_ID,
            "domain": _lever_to_domain(lever),
            "result": {"summary": sig.get("summary", "")},
            "metrics": metrics,
            "context": {
                "cadence": sig.get("cadence"),
                "lever": lever,
                "severity": sig.get("severity", "info"),
            },
            "created_at": f"{date_str}T12:00:00+00:00",
            "processed_by_bm": False,
        })

        episode_id = f"ep-sig-{hashlib.md5((json.dumps(sig, sort_keys=True) + str(i)).encode()).hexdigest()[:12]}"

        predicted_signal = _metrics_to_signal(metrics)
        observed_signal = predicted_signal * (0.85 + hash(episode_id) % 30 / 100)

        episodes.append({
            "episode_id": episode_id,
            "tenant_id": TENANT_ID,
            "skill_name": source_task,
            "domain": _lever_to_domain(lever),
            "prediction": {
                "skill_name": source_task,
                "tenant_id": TENANT_ID,
                "domain": _lever_to_domain(lever),
                "expected_signal": round(predicted_signal, 4),
                "expected_baseline": 1.0,
                "confidence": 0.5,
                "context": {
                    "cadence": sig.get("cadence"),
                    "lever": lever,
                },
            },
            "outcome": {
                "observed_signal": round(observed_signal, 4),
                "goal_completed": sig.get("severity") != "warning",
                "business_impact": metrics.get("spend", 0),
                "prediction_error": round(abs(predicted_signal - observed_signal), 4),
            },
            "weight": 0.6 if sig.get("cadence") == "daily" else 0.8,
            "prediction_error": round(abs(predicted_signal - observed_signal), 4),
            "source": "mh-os",
            "created_at": f"{date_str}T12:00:00+00:00",
        })

    if events:
        db.table("events").upsert(events, on_conflict="id").execute()
    if episodes:
        db.table("episodic_memory").upsert(episodes, on_conflict="episode_id").execute()

    return len(events), len(episodes)


def seed_build_log(db):
    """Seed events + episodic_memory from build-log.jsonl."""
    path = os.path.join(MHOS_ROOT, "20_intelligence/build-log/build-log.jsonl")
    if not os.path.exists(path):
        print(f"  [SKIP] {path} not found")
        return 0, 0

    entries = load_jsonl(path)
    events = []
    episodes = []

    for entry in entries:
        event_id = str(uuid.uuid4())
        date_str = entry.get("date", "2026-03-17")
        lever = entry.get("lever") or "infrastructure"
        numbers = entry.get("numbers", {})

        events.append({
            "id": event_id,
            "source": "mh-os",
            "event_type": "skill_completed",
            "skill_name": "mh-os-build",
            "client_id": TENANT_ID,
            "domain": _lever_to_domain(lever),
            "result": {
                "summary": entry.get("summary", ""),
                "artifacts": entry.get("artifacts", []),
                "decisions": entry.get("decisions", []),
            },
            "metrics": numbers,
            "context": {
                "lever": lever,
                "areas": entry.get("areas", []),
                "bip_angle": entry.get("bip_angle", ""),
            },
            "created_at": f"{date_str}T{entry.get('time', '12:00')}:00+00:00",
            "processed_by_bm": False,
        })

        episode_id = f"ep-build-{date_str}-{entry.get('time', '0000').replace(':', '')}"
        productivity = len(entry.get("artifacts", [])) * 0.1 + len(entry.get("decisions", [])) * 0.05
        productivity = min(1.0, productivity)

        episodes.append({
            "episode_id": episode_id,
            "tenant_id": TENANT_ID,
            "skill_name": "mh-os-build",
            "domain": _lever_to_domain(lever),
            "prediction": {
                "skill_name": "mh-os-build",
                "tenant_id": TENANT_ID,
                "domain": _lever_to_domain(lever),
                "expected_signal": 0.5,
                "expected_baseline": 1.0,
                "confidence": 0.4,
                "context": {"lever": lever},
            },
            "outcome": {
                "observed_signal": round(productivity, 4),
                "goal_completed": True,
                "business_impact": 0,
                "prediction_error": round(abs(0.5 - productivity), 4),
            },
            "weight": 0.9,
            "prediction_error": round(abs(0.5 - productivity), 4),
            "source": "mh-os",
            "created_at": f"{date_str}T{entry.get('time', '12:00')}:00+00:00",
        })

    if events:
        db.table("events").upsert(events, on_conflict="id").execute()
    if episodes:
        db.table("episodic_memory").upsert(episodes, on_conflict="episode_id").execute()

    return len(events), len(episodes)


def seed_deal_outcomes(db):
    """Seed events from linkedin-assisted-deals.csv."""
    path = os.path.join(MHOS_ROOT, "research/artifacts/linkedin-assisted-deals.csv")
    if not os.path.exists(path):
        print(f"  [SKIP] {path} not found")
        return 0

    events = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            revenue = 0
            try:
                revenue = float(row.get("gross_revenue") or 0)
            except ValueError:
                pass

            impressions = 0
            try:
                impressions = int(row.get("li_impressions") or 0)
            except ValueError:
                pass

            events.append({
                "id": str(uuid.uuid4()),
                "source": "mh-os",
                "event_type": "signal",
                "skill_name": "linkedin-ads-attribution",
                "client_id": TENANT_ID,
                "domain": "revenue",
                "result": {
                    "deal_name": row.get("dealname", ""),
                    "company": row.get("company_name", ""),
                },
                "metrics": {
                    "gross_revenue": revenue,
                    "li_impressions": impressions,
                    "li_spend_usd": float(row.get("li_spend_usd") or 0),
                    "is_first_deal": row.get("is_first_deal") == "True",
                },
                "context": {
                    "company_domain": row.get("company_domain", ""),
                    "signed_date": row.get("signed_date", ""),
                },
                "created_at": f"{row.get('signed_date', '2026-01-01')}T12:00:00+00:00"
                    if row.get("signed_date") else datetime.now(timezone.utc).isoformat(),
                "processed_by_bm": False,
            })

    if events:
        for batch_start in range(0, len(events), 50):
            batch = events[batch_start:batch_start + 50]
            db.table("events").upsert(batch, on_conflict="id").execute()

    return len(events)


def seed_semantic_patterns(db):
    """Create a few starter semantic patterns from aggregated signal data."""
    patterns = [
        {
            "pattern_id": "sp-daily-pulse-spend-deviation",
            "skill_name": "daily-pulse",
            "domain": "campaign",
            "pattern_level": "universal",
            "condition": {"lever": "All", "cadence": "daily", "metric": "spend"},
            "recommendation": {
                "description": "Daily spend deviations >20% from mean correlate with FF drop next day",
                "action": "flag_spend_anomaly",
            },
            "confidence": 0.65,
            "expected_value": 0.8,
            "evidence_count": 12,
            "successes": 8,
            "failures": 4,
            "recent_accuracy": 0.67,
        },
        {
            "pattern_id": "sp-weekly-channel-rebalance",
            "skill_name": "channel-advisor",
            "domain": "campaign",
            "pattern_level": "universal",
            "condition": {"lever": "Lead Volume", "cadence": "weekly"},
            "recommendation": {
                "description": "Channel CPA degradation detected weekly predicts budget reallocation need",
                "action": "recommend_rebalance",
            },
            "confidence": 0.55,
            "expected_value": 0.7,
            "evidence_count": 5,
            "successes": 3,
            "failures": 2,
            "recent_accuracy": 0.6,
        },
        {
            "pattern_id": "sp-meta-ff-weekend-drop",
            "skill_name": "meta-social-weekly",
            "domain": "campaign",
            "pattern_level": "segment",
            "condition": {"lever": "Lead Volume", "channel": "meta", "day_type": "weekend"},
            "recommendation": {
                "description": "Meta form fills consistently drop 40-60% on weekends vs weekday avg",
                "action": "adjust_weekend_bids",
            },
            "confidence": 0.72,
            "expected_value": 0.85,
            "evidence_count": 8,
            "successes": 6,
            "failures": 2,
            "recent_accuracy": 0.75,
        },
        {
            "pattern_id": "sp-google-qs-ctr-fix",
            "skill_name": "google-ads-qs",
            "domain": "campaign",
            "pattern_level": "universal",
            "condition": {"lever": "Lead Volume", "qs_range": "1-4"},
            "recommendation": {
                "description": "67% of keywords with below-avg Expected CTR — ad copy is root cause, not structure",
                "action": "rewrite_ad_copy",
                "projected_savings_monthly": 5329,
            },
            "confidence": 0.78,
            "expected_value": 0.9,
            "evidence_count": 3,
            "successes": 2,
            "failures": 1,
            "recent_accuracy": 0.67,
        },
        {
            "pattern_id": "sp-competitive-web-stable",
            "skill_name": "competitive-web-intel",
            "domain": "content",
            "pattern_level": "universal",
            "condition": {"lever": "Lead Volume", "cadence": "weekly"},
            "recommendation": {
                "description": "Competitor web pages are mostly stable week-over-week — reduce scrape frequency",
                "action": "reduce_cadence",
            },
            "confidence": 0.6,
            "expected_value": 0.5,
            "evidence_count": 4,
            "successes": 3,
            "failures": 1,
            "recent_accuracy": 0.75,
        },
    ]

    db.table("semantic_patterns").upsert(patterns, on_conflict="pattern_id").execute()
    return len(patterns)


def _lever_to_domain(lever):
    lever = (lever or "").lower()
    if "revenue" in lever or "deal" in lever or "retention" in lever:
        return "revenue"
    if "lead" in lever or "acquisition" in lever:
        return "campaign"
    if "cvr" in lever or "conversion" in lever or "on-site" in lever:
        return "campaign"
    if "content" in lever or "seo" in lever or "segment" in lever:
        return "content"
    return "generic"


def _metrics_to_signal(metrics):
    if not metrics:
        return 0.5
    if "spend" in metrics and "ff" in metrics:
        ff = metrics["ff"]
        return min(1.0, ff / 50) if ff else 0.1
    if "sessions" in metrics:
        rate = metrics.get("session_to_form_rate", 5)
        return min(1.0, rate / 15)
    if "total_ads" in metrics:
        return min(1.0, metrics.get("avg_ctr", 1) / 3)
    return 0.5


def main():
    print("BrightMatter Test Seed — from MH-OS data")
    print("=" * 50)

    db = get_supabase()

    print("\n1. Seeding signals...")
    ev, ep = seed_signals(db)
    print(f"   {ev} events, {ep} episodes")

    print("\n2. Seeding build log...")
    ev2, ep2 = seed_build_log(db)
    print(f"   {ev2} events, {ep2} episodes")

    print("\n3. Seeding deal outcomes...")
    deals = seed_deal_outcomes(db)
    print(f"   {deals} deal events")

    print("\n4. Seeding semantic patterns...")
    patterns = seed_semantic_patterns(db)
    print(f"   {patterns} patterns")

    print("\n" + "=" * 50)
    print(f"TOTAL: {ev + ev2 + deals} events, {ep + ep2} episodes, {patterns} patterns")

    # Verify
    print("\nVerification:")
    for table in ["events", "episodic_memory", "semantic_patterns"]:
        result = db.table(table).select("*", count="exact").limit(0).execute()
        print(f"  {table}: {result.count} rows")


if __name__ == "__main__":
    main()
