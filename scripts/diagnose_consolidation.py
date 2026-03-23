#!/usr/bin/env python3
"""
BrightMatter Consolidation Diagnostic Script

Tests each stage of the consolidation pipeline independently to identify
where failures occur. Run with real Firebase credentials.

Usage:
    python scripts/diagnose_consolidation.py
    python scripts/diagnose_consolidation.py --tenant-id <tenant_id>
    python scripts/diagnose_consolidation.py --verbose
"""

import argparse
import logging
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def check_storage():
    """Test storage connectivity — Supabase preferred, Firebase fallback."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    using_supabase = bool(supabase_url)

    if using_supabase:
        return _check_supabase()
    return _check_firebase()


def _check_supabase():
    """Test Supabase connectivity."""
    print("\n" + "=" * 60)
    print("1. SUPABASE CONNECTIVITY")
    print("=" * 60)

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    print(f"  SUPABASE_URL: {'SET' if supabase_url else 'MISSING'}")
    print(f"  SUPABASE_KEY: {'SET' if supabase_key else 'MISSING'}")

    if not supabase_url or not supabase_key:
        print("  [FAIL] SUPABASE_URL and SUPABASE_KEY must be set")
        return None

    try:
        from lib.supabase_storage import SupabaseStorage
        storage = SupabaseStorage()
        print("  [OK] SupabaseStorage adapter initialized")

        from lib.supabase_client import get_supabase
        db = get_supabase()
        result = db.table("episodic_memory").select("episode_id", count="exact").limit(1).execute()
        count = getattr(result, "count", None) or (len(result.data) if result.data else 0)
        print(f"  [OK] episodic_memory table accessible ({count} episodes)")

        result = db.table("semantic_patterns").select("pattern_id", count="exact").limit(1).execute()
        count = getattr(result, "count", None) or (len(result.data) if result.data else 0)
        print(f"  [OK] semantic_patterns table accessible ({count} patterns)")

        return storage
    except Exception as e:
        print(f"  [FAIL] Supabase initialization failed: {e}")
        traceback.print_exc()
        return None


def _check_firebase():
    """Test Firebase connectivity."""
    print("\n" + "=" * 60)
    print("1. FIREBASE CONNECTIVITY")
    print("=" * 60)

    cred_json = (
        os.environ.get("SA_JSON", "")
        or os.environ.get("SA_JSON_KEY", "")
        or os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
        or os.environ.get("SERVICE_ACCOUNT_KEY", "")
    )
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    sa_key_path = os.environ.get("SERVICE_ACCOUNT_KEY_PATH", "")
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "") or os.environ.get("GCP_PROJECT_ID", "")

    has_json = cred_json and cred_json.strip().startswith("{")
    has_file = (
        (cred_json and os.path.isfile(cred_json))
        or (sa_key_path and os.path.isfile(sa_key_path))
        or (cred_path and os.path.isfile(cred_path))
    )

    print(f"  Project ID: {'SET' if project_id else 'MISSING'} ({project_id})")
    print(f"  Inline JSON credential: {'YES' if has_json else 'NO'}")
    print(f"  File-based credential: {'YES' if has_file else 'NO'}")

    if not has_json and not has_file:
        print()
        print("  [FAIL] No valid Firebase credentials found in this environment.")
        print()
        print("  To fix, set SUPABASE_URL + SUPABASE_KEY for Supabase storage,")
        print("  or set FIREBASE_CREDENTIALS_JSON for Firebase storage.")
        return None

    try:
        from lib.firebase_client import get_firebase_client
        fb = get_firebase_client()
        print(f"  [OK] Firebase client initialized (project: {getattr(fb, '_project_id', 'unknown')})")

        test_doc = fb.get_document("system", "intelligence")
        if test_doc:
            print(f"  [OK] system/intelligence doc exists: keys={list(test_doc.keys())[:5]}")
        else:
            print("  [WARN] system/intelligence doc not found (may be using subcollections only)")

        return fb
    except Exception as e:
        print(f"  [FAIL] Firebase initialization failed: {e}")
        traceback.print_exc()
        return None


def check_episodic_store(fb):
    """Test episodic memory store methods."""
    print("\n" + "=" * 60)
    print("2. EPISODIC STORE")
    print("=" * 60)
    try:
        from lib.intelligence.memory.episodic import EpisodicMemoryStore, EpisodicMemoryConfig
        store = EpisodicMemoryStore(firebase_client=fb, config=EpisodicMemoryConfig())
        print("  [OK] EpisodicMemoryStore created")

        # 2A: _list_tenants
        print("\n  2A. _list_tenants()")
        tenants = store._list_tenants()
        print(f"  [{'OK' if tenants else 'WARN'}] Tenants found: {tenants} (count={len(tenants)})")

        if not tenants:
            print("  [ISSUE] No tenants found — consolidation will short-circuit")
            print("  [HINT] Episodes may not be stored, or Firebase path may be wrong")
            print("  [HINT] Expected path: system/intelligence/episodic/{tenant_id}/...")
            return store, [], {}

        # 2B: _list_skills_for_tenant
        tenant_skills = {}
        for tid in tenants[:3]:
            print(f"\n  2B. _list_skills_for_tenant('{tid}')")
            skills = store._list_skills_for_tenant(tid)
            tenant_skills[tid] = skills
            print(f"  [{'OK' if skills else 'WARN'}] Skills: {skills} (count={len(skills)})")

        # 2C: get_for_consolidation
        all_ready = {}
        for tid, skills in tenant_skills.items():
            for skill in skills[:3]:
                print(f"\n  2C. get_for_consolidation('{tid}', '{skill}')")
                ready = store.get_for_consolidation(tenant_id=tid, skill_name=skill, limit=20)
                all_ready[(tid, skill)] = ready
                print(f"  [{'OK' if ready else 'INFO'}] Ready episodes: {len(ready)}")
                if ready:
                    ep = ready[0]
                    print(f"       First episode: id={ep.episode_id}")
                    print(f"         weight={ep.weight:.4f}, consolidated_at={ep.consolidated_at}")
                    print(f"         prediction.skill={ep.prediction.skill_name}")
                    print(f"         prediction.domain={ep.prediction.domain}")
                    ctx = ep.prediction.context
                    print(f"         prediction.context keys={list(ctx.keys()) if ctx else 'EMPTY'}")
                    print(f"         outcome.goal_completed={ep.outcome.goal_completed}")
                    print(f"         outcome.observed_signal={ep.outcome.observed_signal}")

        # 2D: Check total episode counts (including non-ready)
        for tid, skills in tenant_skills.items():
            for skill in skills[:3]:
                try:
                    collection_path = store._get_collection_path(tid, skill)
                    all_docs = fb.get_collection(collection=collection_path)
                    total = len(all_docs) if all_docs else 0
                    ready_count = len(all_ready.get((tid, skill), []))
                    print(f"\n  2D. Episode counts for {tid}/{skill}:")
                    print(f"       total={total}, ready_for_consolidation={ready_count}")
                    if total > 0 and ready_count == 0:
                        print("       [HINT] Episodes exist but none ready — decay may not be reducing weights")
                        if all_docs:
                            sample = all_docs[0]
                            w = sample.get("weight", "MISSING")
                            ca = sample.get("consolidated_at", "MISSING")
                            print(f"       Sample: weight={w}, consolidated_at={ca}")
                except Exception as e:
                    print(f"  [WARN] Could not count episodes for {tid}/{skill}: {e}")

        return store, tenants, tenant_skills

    except Exception as e:
        print(f"  [FAIL] EpisodicMemoryStore error: {e}")
        traceback.print_exc()
        return None, [], {}


def check_semantic_store(fb):
    """Test semantic memory store methods."""
    print("\n" + "=" * 60)
    print("3. SEMANTIC STORE")
    print("=" * 60)
    try:
        from lib.intelligence.memory.semantic import SemanticMemoryStore, SemanticMemoryConfig
        store = SemanticMemoryStore(firebase_client=fb, config=SemanticMemoryConfig())
        print("  [OK] SemanticMemoryStore created")

        has_consolidate = hasattr(store, 'consolidate_episodes')
        has_from_episodes = hasattr(store, 'consolidate_from_episodes')
        has_forget = hasattr(store, 'forget_stale_patterns')
        has_high_conf = hasattr(store, 'get_high_confidence_patterns')

        print(f"  consolidate_episodes: {'YES' if has_consolidate else 'MISSING'}")
        print(f"  consolidate_from_episodes: {'YES' if has_from_episodes else 'MISSING'}")
        print(f"  forget_stale_patterns: {'YES' if has_forget else 'MISSING'}")
        print(f"  get_high_confidence_patterns: {'YES' if has_high_conf else 'MISSING'}")

        return store
    except Exception as e:
        print(f"  [FAIL] SemanticMemoryStore error: {e}")
        traceback.print_exc()
        return None


def check_procedural_store(fb):
    """Test procedural memory store methods."""
    print("\n" + "=" * 60)
    print("4. PROCEDURAL STORE")
    print("=" * 60)
    try:
        from lib.intelligence.memory.procedural import ProceduralMemoryStore, ProceduralMemoryConfig
        store = ProceduralMemoryStore(firebase_client=fb, config=ProceduralMemoryConfig())
        print("  [OK] ProceduralMemoryStore created")

        has_create = hasattr(store, 'create_from_patterns')
        has_decay = hasattr(store, 'decay_all')
        print(f"  create_from_patterns: {'YES' if has_create else 'MISSING'}")
        print(f"  decay_all: {'YES' if has_decay else 'MISSING'}")

        return store
    except Exception as e:
        print(f"  [FAIL] ProceduralMemoryStore error: {e}")
        traceback.print_exc()
        return None


def run_full_consolidation(tenant_id=None):
    """Run the full consolidation cycle via IntelligenceEngine."""
    print("\n" + "=" * 60)
    print("5. FULL CONSOLIDATION CYCLE")
    print("=" * 60)
    try:
        from lib.intelligence import IntelligenceEngine
        engine = IntelligenceEngine()
        print("  [OK] IntelligenceEngine created")

        print(f"  Running consolidation (tenant={tenant_id or 'all'})...")
        stats = engine.run_consolidation(tenant_id=tenant_id)
        print(f"  [OK] Consolidation returned: {stats}")

        if stats.get("episodes_consolidated", 0) == 0:
            print("  [WARN] Zero episodes consolidated")
        if stats.get("patterns_created", 0) == 0 and stats.get("patterns_updated", 0) == 0:
            print("  [WARN] No patterns created or updated")

        return stats
    except Exception as e:
        print(f"  [FAIL] Consolidation error: {e}")
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="Diagnose BrightMatter consolidation pipeline")
    parser.add_argument("--tenant-id", help="Specific tenant to test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--skip-full", action="store_true", help="Skip full consolidation run")
    args = parser.parse_args()

    setup_logging(args.verbose)

    print("BrightMatter Consolidation Diagnostic")
    print("=" * 60)

    storage = check_storage()
    if storage is None:
        print("\n[ABORT] Cannot proceed without storage backend")
        sys.exit(1)

    backend = "Supabase" if os.environ.get("SUPABASE_URL") else "Firebase"
    print(f"\n  Backend: {backend}")

    episodic_store, tenants, tenant_skills = check_episodic_store(storage)
    semantic_store = check_semantic_store(storage)
    procedural_store = check_procedural_store(storage)

    if not args.skip_full:
        run_full_consolidation(tenant_id=args.tenant_id)

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    if not tenants:
        print("ROOT CAUSE: No tenants found in episodic store")
        print("  → Episodes are not being stored, OR Firebase path is wrong")
    elif all(len(v) == 0 for v in tenant_skills.values()):
        print("ROOT CAUSE: Tenants exist but no skill subcollections found")
        print("  → Subcollection enumeration may be failing")
    else:
        print("Store methods appear functional. Check [CONSOLIDATION] log output above")
        print("for the exact step where the pipeline stalls.")


if __name__ == "__main__":
    main()
