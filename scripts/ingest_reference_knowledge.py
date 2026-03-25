"""
Ingest reference knowledge from DTC-OS into BrightMatter's
reference_knowledge Supabase table.

Sources:
  - Expert Panel evaluation profiles (9 experts)
  - Tactics Vault (579 tactics)
  - Ad Vault (238 ad examples)
  - B2C Tech Path courses (44 lessons)

Usage:
    python scripts/ingest_reference_knowledge.py --all
    python scripts/ingest_reference_knowledge.py --experts
    python scripts/ingest_reference_knowledge.py --tactics
    python scripts/ingest_reference_knowledge.py --ads
    python scripts/ingest_reference_knowledge.py --courses
    python scripts/ingest_reference_knowledge.py --create-table
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from lib.supabase_client import get_supabase

logger = logging.getLogger("ingest_reference_knowledge")

DTC_OS_ROOT = Path(os.environ.get(
    "DTC_OS_PATH", "/Applications/MH1/DTC-OS"
))

TABLE = "reference_knowledge"

# ── Tag inference helpers ──────────────────────────────────────────

_TAG_KEYWORDS = {
    "meta-ads": ["meta", "facebook", "instagram", "fb ", "ig "],
    "google-ads": ["google ads", "google search", "pmax", "performance max", "google shopping"],
    "tiktok-ads": ["tiktok"],
    "seo": ["seo", "search engine"],
    "email": ["email", "lifecycle", "drip", "newsletter"],
    "cro": ["cro", "conversion", "checkout", "landing page", "a/b test"],
    "retention": ["retention", "churn", "reactivation"],
    "pricing": ["pricing", "monetization", "arpu", "aov"],
    "copy": ["copy", "headline", "hook", "persuasion"],
    "creative": ["creative", "ad creative", "visual"],
    "growth": ["growth", "flywheel", "acquisition"],
    "analytics": ["analytics", "measurement", "attribution"],
    "positioning": ["positioning", "messaging", "differentiation"],
    "community": ["community", "word of mouth", "referral"],
    "content": ["content marketing", "organic"],
    "onboarding": ["onboarding", "activation"],
    "strategy": ["strategy", "funnel", "go-to-market", "gtm"],
    "roas": ["roas", "return on ad spend"],
}

_LEVER_KEYWORDS = {
    "CVR": ["conversion", "checkout", "cro", "landing page"],
    "AOV": ["aov", "upsell", "pricing", "cart"],
    "Sessions": ["traffic", "seo", "ads", "acquisition"],
    "Retention": ["retention", "churn", "ltv", "lifecycle"],
    "CAC": ["cac", "cost per", "cpa", "acquisition cost"],
    "LTV": ["ltv", "lifetime value", "clv"],
    "ROAS": ["roas", "return on ad spend"],
}

_CATEGORY_MAP = {
    "Ads": "advertising",
    "Experimentation": "growth",
    "CRO": "cro",
    "Strategy": "strategy",
    "Retention": "retention",
    "Analytics": "analytics",
    "Email": "retention",
    "Landing pages": "cro",
    "Copy": "persuasion",
    "Pricing": "strategy",
    "SEO": "growth",
    "Growth": "growth",
    "Content": "strategy",
    "Community": "growth",
}


def _infer_tags(text: str) -> List[str]:
    lower = text.lower()
    return [tag for tag, kws in _TAG_KEYWORDS.items() if any(k in lower for k in kws)]


def _infer_levers(text: str) -> List[str]:
    lower = text.lower()
    return [lev for lev, kws in _LEVER_KEYWORDS.items() if any(k in lower for k in kws)]


def _normalize_category(raw: str) -> str:
    return _CATEGORY_MAP.get(raw, raw.lower().replace(" ", "_") if raw else "strategy")


# ── Table creation ─────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reference_knowledge (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  content JSONB NOT NULL DEFAULT '{}',
  tags TEXT[] DEFAULT '{}',
  levers TEXT[] DEFAULT '{}',
  expert_handle TEXT,
  confidence_weight FLOAT DEFAULT 0.7,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refknow_source ON reference_knowledge(source);
CREATE INDEX IF NOT EXISTS idx_refknow_category ON reference_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_refknow_tags ON reference_knowledge USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_refknow_levers ON reference_knowledge USING GIN(levers);
CREATE INDEX IF NOT EXISTS idx_refknow_expert ON reference_knowledge(expert_handle)
  WHERE expert_handle IS NOT NULL;
"""


def create_table():
    db = get_supabase()
    try:
        db.rpc("exec_sql", {"query": CREATE_TABLE_SQL}).execute()
        logger.info("reference_knowledge table created via RPC")
    except Exception:
        logger.info(
            "RPC exec_sql not available — run the SQL in schema/supabase_tables.sql "
            "directly in the Supabase SQL editor."
        )


# ── Batch upsert ───────────────────────────────────────────────────

def _batch_upsert(rows: List[Dict[str, Any]], source_label: str):
    db = get_supabase()

    existing = (
        db.table(TABLE)
        .select("id,title,source")
        .eq("source", source_label)
        .execute()
    )
    existing_titles = {r["title"] for r in (existing.data or [])}

    new_rows = [r for r in rows if r["title"] not in existing_titles]
    if not new_rows:
        logger.info(f"[{source_label}] All {len(rows)} rows already exist — skipping")
        return 0

    BATCH = 50
    inserted = 0
    for i in range(0, len(new_rows), BATCH):
        batch = new_rows[i:i + BATCH]
        try:
            db.table(TABLE).insert(batch).execute()
            inserted += len(batch)
            logger.info(f"[{source_label}] Inserted batch {i // BATCH + 1} ({len(batch)} rows)")
        except Exception as e:
            logger.warning(f"[{source_label}] Batch insert failed: {e}")

    logger.info(f"[{source_label}] Done — {inserted}/{len(rows)} new rows inserted")
    return inserted


# ── Expert Panel Ingestion ─────────────────────────────────────────

def ingest_experts() -> int:
    base = DTC_OS_ROOT / "expert-panel" / "dimensions"
    if not base.exists():
        logger.warning(f"Expert panel not found at {base}")
        return 0

    rows: List[Dict[str, Any]] = []
    for profile_path in sorted(base.rglob("evaluation_profile.json")):
        try:
            data = json.loads(profile_path.read_text())
        except Exception as e:
            logger.warning(f"Failed to parse {profile_path}: {e}")
            continue

        identity = data.get("identity", {})
        handle = identity.get("handle", "")
        name = identity.get("name", "")
        domain = identity.get("domain", "")
        dimension = identity.get("dimension", "")
        thesis = identity.get("core_thesis", "")
        blindspots = identity.get("blindspots", [])

        dim_category = dimension.split("-", 1)[-1].replace("-", "_") if dimension else "strategy"
        category = _normalize_category(dim_category) if dim_category not in _CATEGORY_MAP.values() else dim_category

        for fw in data.get("frameworks", []):
            fw_name = fw.get("name", "Unknown")
            fw_source = fw.get("source", "")
            fw_purpose = fw.get("purpose", "")
            fw_mechanics = fw.get("mechanics", "")

            instant_fails = []
            scoring_rubrics = []
            for comp in fw.get("components", []):
                scoring = comp.get("scoring", {})
                if scoring.get("instant_fail"):
                    instant_fails.append({
                        "component": comp.get("name", ""),
                        "rule": scoring["instant_fail"],
                    })
                scoring_rubrics.append({
                    "component": comp.get("name", ""),
                    "definition": comp.get("definition", ""),
                    "criteria": comp.get("evaluation_criteria", ""),
                    "high": scoring.get("high", ""),
                    "low": scoring.get("low", ""),
                })

            summary = f"{name}: {fw_purpose[:150]}" if fw_purpose else f"{name}: {fw_name}"
            searchable = f"{fw_name} {fw_purpose} {fw_mechanics} {domain}"
            tags = _infer_tags(searchable) + [handle]
            levers = _infer_levers(searchable)

            rows.append({
                "source": "expert-panel",
                "category": category,
                "title": f"{handle}/{fw_name}",
                "summary": summary[:200],
                "content": {
                    "expert_name": name,
                    "framework_name": fw_name,
                    "framework_source": fw_source,
                    "purpose": fw_purpose,
                    "mechanics": fw_mechanics,
                    "core_thesis": thesis,
                    "blindspots": blindspots,
                    "instant_fail_rules": instant_fails,
                    "scoring_rubrics": scoring_rubrics,
                    "decision_rules": data.get("decision_rules", []),
                },
                "tags": list(set(tags)),
                "levers": list(set(levers)),
                "expert_handle": handle,
                "confidence_weight": 1.0,
            })

    logger.info(f"Prepared {len(rows)} expert framework rows from {base}")
    return _batch_upsert(rows, "expert-panel")


# ── Tactics Vault Ingestion ────────────────────────────────────────

def ingest_tactics() -> int:
    index_path = DTC_OS_ROOT / "frameworks" / "tactics-vault" / "tactics-index.json"
    if not index_path.exists():
        logger.warning(f"Tactics index not found at {index_path}")
        return 0

    try:
        tactics = json.loads(index_path.read_text())
    except Exception as e:
        logger.warning(f"Failed to parse tactics index: {e}")
        return 0

    rows: List[Dict[str, Any]] = []
    for t in tactics:
        title = t.get("title", "")
        if not title:
            continue

        body = t.get("body", "")
        tag = t.get("tag", "")
        source_attr = t.get("source", "")
        slug = t.get("slug", "")

        category = _normalize_category(tag)
        searchable = f"{title} {body[:500]} {tag}"
        tags = _infer_tags(searchable) + ([tag.lower().replace(" ", "-")] if tag else [])
        levers = _infer_levers(searchable)

        body_preview = body[:300].replace("\n", " ").strip()
        summary = f"{body_preview}..." if len(body) > 300 else body_preview

        rows.append({
            "source": "tactics-vault",
            "category": category,
            "title": title,
            "summary": summary[:200],
            "content": {
                "body": body[:5000],
                "tag": tag,
                "attribution": source_attr,
                "slug": slug,
                "edition_url": t.get("edition_url", ""),
            },
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": 0.7,
        })

    logger.info(f"Prepared {len(rows)} tactic rows")
    return _batch_upsert(rows, "tactics-vault")


# ── Ad Vault Ingestion ─────────────────────────────────────────────

def ingest_ads() -> int:
    index_path = DTC_OS_ROOT / "frameworks" / "ad-vault" / "ad-vault-index.json"
    if not index_path.exists():
        logger.warning(f"Ad vault index not found at {index_path}")
        return 0

    try:
        ads = json.loads(index_path.read_text())
    except Exception as e:
        logger.warning(f"Failed to parse ad vault index: {e}")
        return 0

    rows: List[Dict[str, Any]] = []
    for ad in ads:
        company = ad.get("company", "Unknown")
        industry = ad.get("industry", "")
        fmt = ad.get("format", "")

        title = f"{company} — {fmt}" if fmt else company
        summary = f"{company} ({industry}) {fmt} ad example"
        tags = ["creative", "advertising"]
        if industry:
            tags.append(industry.lower().replace(" ", "-"))
        if fmt:
            tags.append(fmt.lower())

        rows.append({
            "source": "ad-vault",
            "category": "advertising",
            "title": title,
            "summary": summary[:200],
            "content": {
                "company": company,
                "industry": industry,
                "format": fmt,
                "image_url": ad.get("image_url", ""),
                "company_url": ad.get("company_url", ""),
                "description": ad.get("description", ""),
            },
            "tags": list(set(tags)),
            "levers": ["CVR"],
            "expert_handle": None,
            "confidence_weight": 0.5,
        })

    logger.info(f"Prepared {len(rows)} ad example rows")
    return _batch_upsert(rows, "ad-vault")


# ── B2C Tech Path Courses ──────────────────────────────────────────

def ingest_courses() -> int:
    base = DTC_OS_ROOT / "frameworks" / "b2c-tech-path"
    if not base.exists():
        logger.warning(f"B2C Tech Path not found at {base}")
        return 0

    rows: List[Dict[str, Any]] = []
    for md_path in sorted(base.glob("*.md")):
        if md_path.name.startswith("00-"):
            continue

        text = md_path.read_text(errors="replace")
        lines = text.split("\n")
        title_line = next((l for l in lines if l.startswith("# ")), "")
        title = title_line.lstrip("# ").strip() or md_path.stem.replace("-", " ").title()

        num_match = re.match(r"(\d+)-", md_path.name)
        lesson_num = int(num_match.group(1)) if num_match else 0

        body_start = next(
            (i for i, l in enumerate(lines) if l.startswith("---")),
            min(5, len(lines)),
        )
        body = "\n".join(lines[body_start + 1:]).strip()

        searchable = f"{title} {body[:1000]}"
        tags = _infer_tags(searchable) + ["demand-curve", "b2c"]
        levers = _infer_levers(searchable)

        first_para = ""
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
                first_para = stripped[:200]
                break

        category_guess = "growth"
        for cat_tag, cat_name in [
            ("seo", "growth"), ("ads", "advertising"), ("email", "retention"),
            ("cro", "cro"), ("pricing", "strategy"), ("copy", "persuasion"),
            ("onboarding", "cro"), ("retention", "retention"),
        ]:
            if cat_tag in title.lower():
                category_guess = cat_name
                break

        rows.append({
            "source": "b2c-courses",
            "category": category_guess,
            "title": title,
            "summary": first_para[:200] if first_para else title,
            "content": {
                "lesson_number": lesson_num,
                "filename": md_path.name,
                "body": body[:8000],
            },
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": 0.7,
        })

    logger.info(f"Prepared {len(rows)} course rows")
    return _batch_upsert(rows, "b2c-courses")


# ── DTC-OS Semantic Layer & Intelligence ──────────────────────────

def ingest_dtc_intelligence() -> int:
    rows: List[Dict[str, Any]] = []

    semantic_files = [
        ("glossary.yaml", "dtc-glossary", "analytics", 0.9,
         "Canonical metric definitions used across DTC-OS signals and reports"),
        ("entities.yaml", "dtc-entities", "analytics", 0.9,
         "Core data entities and relationships for Shopify-based DTC brands"),
        ("cohort-methodology.md", "dtc-cohort-methodology", "analytics", 1.0,
         "When to use real-time vs cohort measurement, minimum sample sizes"),
    ]
    sem_dir = DTC_OS_ROOT / "00_data" / "semantic-layer"
    for fname, title_slug, category, weight, summary in semantic_files:
        fpath = sem_dir / fname
        if not fpath.exists():
            logger.warning(f"Semantic layer file not found: {fpath}")
            continue
        text = fpath.read_text(errors="replace")
        tags = _infer_tags(text) + ["dtc", "semantic-layer"]
        levers = _infer_levers(text)
        rows.append({
            "source": "dtc-semantic-layer",
            "category": category,
            "title": title_slug,
            "summary": summary[:200],
            "content": {"body": text[:10000], "filename": fname},
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": weight,
        })

    intel_files = [
        ("driver-tree.md", "dtc-driver-tree", "strategy", 1.0,
         "Revenue decomposition tree mapping every lever to execution modules"),
        ("compounding-loops.md", "dtc-compounding-loops", "strategy", 0.9,
         "6 virtuous cycles where each execution output feeds the next"),
        ("growth-analytics-advisory.md", "growth-analytics-advisory", "analytics", 0.9,
         "L1/L2/L3 reporting framework for strategic, tactical, and operational decisions"),
    ]
    intel_dir = DTC_OS_ROOT / "20_intelligence"
    for fname, title_slug, category, weight, summary in intel_files:
        fpath = intel_dir / fname
        if not fpath.exists():
            continue
        text = fpath.read_text(errors="replace")
        tags = _infer_tags(text) + ["dtc", "intelligence"]
        levers = _infer_levers(text)
        rows.append({
            "source": "dtc-intelligence",
            "category": category,
            "title": title_slug,
            "summary": summary[:200],
            "content": {"body": text[:10000], "filename": fname},
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": weight,
        })

    strat_dir = DTC_OS_ROOT / "30_strategy"
    for md_path in sorted(strat_dir.glob("*.md")) if strat_dir.exists() else []:
        text = md_path.read_text(errors="replace")
        lines = text.split("\n")
        title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), md_path.stem)
        tags = _infer_tags(text) + ["dtc", "strategy"]
        levers = _infer_levers(text)
        first_para = next(
            (l.strip()[:200] for l in lines if l.strip() and not l.startswith("#") and not l.startswith(">")),
            title,
        )
        rows.append({
            "source": "dtc-strategy",
            "category": "strategy",
            "title": md_path.stem,
            "summary": first_para[:200],
            "content": {"body": text[:8000], "filename": md_path.name},
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": 0.8,
        })

    logger.info(f"Prepared {len(rows)} DTC-OS intelligence rows")
    if not rows:
        return 0
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)
    total = 0
    for src, src_rows in by_source.items():
        total += _batch_upsert(src_rows, src)
    return total


# ── MH-OS Domain Knowledge ───────────────────────────────────────

def ingest_mhos_knowledge() -> int:
    MH_OS_ROOT = Path(os.environ.get("MH_OS_PATH", "/Applications/MH1/mh-os"))
    rows: List[Dict[str, Any]] = []

    shared_dir = MH_OS_ROOT / "src" / "trigger" / "shared"
    if shared_dir.exists():
        for ts_file in sorted(shared_dir.glob("*.ts")):
            text = ts_file.read_text(errors="replace")
            if len(text) < 100:
                continue
            tags = _infer_tags(text) + ["mh-os", "trigger-dev"]
            rows.append({
                "source": "mhos-trigger-patterns",
                "category": "strategy",
                "title": f"mhos-shared/{ts_file.stem}",
                "summary": f"MH-OS shared module: {ts_file.stem} — reusable patterns for trigger tasks",
                "content": {"filename": ts_file.name, "module_type": "shared"},
                "tags": list(set(tags)),
                "levers": [],
                "expert_handle": None,
                "confidence_weight": 0.6,
            })

    trigger_dirs = [
        ("channel-advisor", "channel-reallocation", "paid_media",
         "Reallocates budget across channels based on performance signals"),
        ("daily-pulse", "daily-health-pulse", "operations",
         "Daily anomaly detection across all client metrics"),
        ("revenue-health", "revenue-monitoring", "revenue",
         "Monthly revenue trend analysis with cohort tracking"),
    ]
    for task_dir, skill, domain, summary in trigger_dirs:
        task_path = MH_OS_ROOT / "src" / "trigger" / task_dir
        if not task_path.exists():
            continue
        main_ts = task_path / f"{task_dir}.ts"
        if not main_ts.exists():
            continue
        text = main_ts.read_text(errors="replace")
        tags = _infer_tags(text) + ["mh-os", "trigger-dev", domain]
        levers = _infer_levers(text)
        rows.append({
            "source": "mhos-triggers",
            "category": domain.replace("_", "-"),
            "title": f"mhos-trigger/{task_dir}",
            "summary": summary[:200],
            "content": {
                "skill_name": skill,
                "domain": domain,
                "filename": main_ts.name,
            },
            "tags": list(set(tags)),
            "levers": list(set(levers)),
            "expert_handle": None,
            "confidence_weight": 0.7,
        })

    logger.info(f"Prepared {len(rows)} MH-OS knowledge rows")
    if not rows:
        return 0
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)
    total = 0
    for src, src_rows in by_source.items():
        total += _batch_upsert(src_rows, src)
    return total


# ── CLI ────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Ingest reference knowledge into BrightMatter")
    parser.add_argument("--create-table", action="store_true", help="Create the Supabase table")
    parser.add_argument("--experts", action="store_true", help="Ingest expert evaluation profiles")
    parser.add_argument("--tactics", action="store_true", help="Ingest tactics vault")
    parser.add_argument("--ads", action="store_true", help="Ingest ad vault examples")
    parser.add_argument("--courses", action="store_true", help="Ingest B2C Tech Path courses")
    parser.add_argument("--dtc", action="store_true", help="Ingest DTC-OS semantic layer + intelligence")
    parser.add_argument("--mhos", action="store_true", help="Ingest MH-OS trigger task knowledge")
    parser.add_argument("--all", action="store_true", help="Run all ingestion sources")
    args = parser.parse_args()

    if args.create_table:
        create_table()
        return

    run_all = args.all or not any([args.experts, args.tactics, args.ads, args.courses, args.dtc, args.mhos])
    totals = {}

    if run_all or args.experts:
        totals["experts"] = ingest_experts()

    if run_all or args.tactics:
        totals["tactics"] = ingest_tactics()

    if run_all or args.ads:
        totals["ads"] = ingest_ads()

    if run_all or args.courses:
        totals["courses"] = ingest_courses()

    if run_all or args.dtc:
        totals["dtc_intelligence"] = ingest_dtc_intelligence()

    if run_all or args.mhos:
        totals["mhos_knowledge"] = ingest_mhos_knowledge()

    logger.info(f"Ingestion complete: {totals}")


if __name__ == "__main__":
    main()
