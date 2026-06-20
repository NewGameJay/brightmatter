"""Phase 6.5 — Forward Deployment scaffold (Modal cron).

Wraps the daily cycle for scheduled execution. The daily cycle is:
  1-2. INGEST new daily_metrics + change_events (live Google Ads pull)
  3-7. PREDICT / RESOLVE / health / live-state  (scripts/daily_run.py logic)
  + monitoring hooks (spec 6.5.1): failure / stale-data / accuracy-floor alerts.

NOTE ON VALIDATION: forward deployment is validated over 30 CALENDAR days of real
operation (predictions made today, resolved in 7-30 days against outcomes that do
not yet exist). That cannot be executed in a build session — this file is the
deployable harness; the 30-day go/no-go (spec 6.5.5) happens in production.

Deploy:   modal deploy scripts/deploy_modal.py
Run once: modal run scripts/deploy_modal.py
Local:    python scripts/deploy_modal.py --local   (no Modal; runs the cycle in-process)

If Modal isn't installed/used, the same cycle runs from cron directly:
  0 5 * * *  cd /path/to/brightmatter && python scripts/deploy_modal.py --local
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Monitoring thresholds (spec 6.5.1)
STALE_DATA_DAYS = 3          # no new episodes for N days -> alert
ACCURACY_FLOOR = 0.55        # rolling-14d decisive rec accuracy below this -> alert


def _alert(channel: str, message: str) -> None:
    """Emit an alert. Wire to Slack/email in production; logs by default so a cron
    failure is always visible in the job output."""
    print(f"[ALERT:{channel}] {message}", flush=True)


def run_cycle(as_of: date | None = None, do_ingest: bool = True) -> dict:
    """The full daily cycle + monitoring. Returns a status dict."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from brightmatter.storage.database import Database
    from brightmatter.storage.repository import Repository
    from brightmatter.patterns import operate, refine

    db = Database(); db.initialize()
    status = {"ok": True, "alerts": []}

    # 1-2. INGEST (live). Failures alert but don't abort the predict/resolve cycle —
    # the loop still operates on existing data.
    if do_ingest:
        try:
            from brightmatter.ingestion.pipeline import IngestionPipeline
            pipe = IngestionPipeline(Repository(db))
            if getattr(pipe, "is_live", False):
                pipe.ingest_daily(days=30)
                pipe.ingest_changes(days=28)
            else:
                status["alerts"].append("ingestion not live (no credentials) — operating on existing data")
        except Exception as e:  # noqa: BLE001
            msg = f"ingestion failed: {e}"
            _alert("pipeline", msg); status["alerts"].append(msg)

    aod = as_of or operate._data_max_date(db)

    # stale-data check
    latest = db.fetchone("SELECT max(date) FROM daily_metrics")[0]
    if latest and (date.today() - latest).days > STALE_DATA_DAYS and as_of is None:
        msg = f"daily_metrics stale: latest={latest}, {(date.today()-latest).days}d old"
        _alert("pipeline", msg); status["alerts"].append(msg)

    # 3. PREDICT / 5. RESOLVE / 6. HEALTH
    eps = [e for e in refine.refine_episodes(db) if e.get("change_date") and e["change_date"] <= aod]
    status["registered"] = operate.register_predictions(db, eps)
    status["resolved"] = operate.resolve_predictions(db, as_of=aod)["newly_resolved"]
    status["health"] = operate.update_template_health(db)

    # 7. REPORT
    operate.generate_live_state(db, str(ROOT / "docs" / "brightmatter-live-state.md"))
    rec = operate.recommendation_accuracy(db, 14)
    if rec.get("decisive_n"):
        acc = rec["decisive_recommendation_accuracy"]
        status["decisive_accuracy_14d"] = acc
        if acc < ACCURACY_FLOOR:
            msg = f"decisive rec accuracy {acc*100:.0f}% < floor {ACCURACY_FLOOR*100:.0f}%"
            _alert("accuracy", msg); status["alerts"].append(msg)

    db.execute("CHECKPOINT"); db.close()
    print(f"[deploy] cycle complete as-of {aod}: {status}", flush=True)
    return status


# ── Modal app (optional; only imported if modal is installed) ──
try:
    import modal  # type: ignore
    app = modal.App("brightmatter-daily")
    image = modal.Image.debian_slim().pip_install_from_requirements(str(ROOT / "requirements.txt")) \
        if (ROOT / "requirements.txt").exists() else modal.Image.debian_slim()

    @app.function(image=image, schedule=modal.Cron("0 5 * * *"), timeout=1800)
    def daily():  # pragma: no cover - runs in Modal
        return run_cycle()
except Exception:
    app = None  # Modal not installed; --local path still works


if __name__ == "__main__":
    local = "--local" in sys.argv
    no_ingest = "--no-ingest" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aod = date.fromisoformat(args[0]) if args else None
    run_cycle(as_of=aod, do_ingest=not no_ingest)
