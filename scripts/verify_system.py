"""BrightMatter verification — one command an auditor runs to verify the whole system.

  python scripts/verify_system.py --backfill   # populate ledger/versions/links/checksums from existing data (run once)
  python scripts/verify_system.py              # verify everything + print trust block
  python scripts/verify_system.py --export      # + write accuracy audit CSV
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from brightmatter.storage.database import Database
from brightmatter.verification import ledger, integrity, versions, provenance, events, health

db = Database(); db.initialize()

if "--backfill" in sys.argv:
    print("[verify] backfilling verification records from existing data…")
    # 1. template_episode_links (which episodes formed each template) — needed by versions
    n_links = provenance.build_template_episode_links(db)
    print(f"  template_episode_links: {n_links}")
    # 2. template_versions (hash + git commit)
    n_ver = versions.snapshot_template_versions(db)
    print(f"  template_versions: {n_ver}")
    # 3. prediction_ledger from live_predictions (chain in registration order)
    preds = db.fetchall("""SELECT prediction_id, template_id, episode_id, account_id, campaign_id,
                                  state, predicted_direction, predicted_magnitude, recommendation, registered_at
                           FROM live_predictions ORDER BY registered_at, prediction_id""")
    n_led = 0
    for p in preds:
        ledger.register_to_ledger(db, {
            "prediction_id": p[0], "template_id": p[1], "episode_id": p[2], "account_id": p[3],
            "campaign_id": p[4], "pre_state": p[5], "predicted_direction": p[6],
            "predicted_magnitude": p[7], "recommendation": p[8], "timestamp": p[9]})
        n_led += 1
    db.execute("CHECKPOINT")
    print(f"  prediction_ledger: {n_led}")
    # 4. ingestion checksums
    ck = integrity.compute_checksums(db)
    print(f"  ingestion_checksums: {ck['checksums']} ({ck['mismatches']} mismatches)")
    # 5. drift events from template_health
    n_ev = events.sync_drift_events(db)
    print(f"  drift events logged: {n_ev}")
    print("[verify] backfill done.\n")

# ── verify everything ──
print("[verify] === INTEGRITY CHECKS ===")
led = ledger.verify_ledger_integrity(db)
print(f"  ledger: {'OK' if led['ok'] else 'BROKEN'} ({led['n']} entries" + (f", break@{led['break_at']}" if not led['ok'] else "") + ")")
ck = integrity.verify_checksums(db)
print(f"  checksums: {'OK' if ck['ok'] else 'MISMATCH'} ({ck['dates_verified']} dates, {ck['mismatches']} changed)")
repro = versions.reproducibility_test(db)
print(f"  reproducibility: {'OK' if repro['ok'] else 'FAIL'} ({repro['checked']} templates, {len(repro['mismatches'])} mismatch)")
if repro["mismatches"][:3]:
    for m in repro["mismatches"][:3]:
        print(f"     - {m}")

events.sync_drift_events(db)
h = health.compute_system_health(db)
print("\n" + health.render_trust_block(h))

if "--export" in sys.argv:
    out = ROOT / "docs" / "accuracy-audit.csv"
    n = provenance.export_accuracy_audit(db, str(out))
    print(f"\n[verify] accuracy audit CSV: {n} rows -> {out}")

# sample provenance / spot-check for one campaign
camp = db.fetchone("""SELECT account_id, campaign_id FROM episodes WHERE campaign_id<>''
                      AND pre_state<>'' GROUP BY 1,2 ORDER BY count(*) DESC LIMIT 1""")
if camp:
    sc = provenance.spot_check(db, camp[0], camp[1])
    print(f"\n[verify] spot-check sample ({camp[1]}, state={sc.get('state')}, action={sc.get('action')}): "
          f"{sc.get('n_examples')} real episodes returned")

db.execute("CHECKPOINT")
print("\n[verify] DONE")
db.close()
