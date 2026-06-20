"""GA4 Phase 1 — Discovery grounding (no GA4 data pull; spec: discovery/research only).

Three reproducible parts:
  1. AUTH PROBE — can we reach the GA4 Admin API with the creds in this env?
  2. DISCOVERY MAPPING — partial GA4<->Ads mapping from data ALREADY in the DB
     (imported-goal linkage, website URLs for URL-match, ecommerce instrumentation).
  3. SIGNAL VALUE — how many BrightMatter signals each GA4 signal could address.

The live GA4 columns (property_id, access, data_months, cwv_enabled) require GA4
API access; where that's unavailable they're emitted as 'pending_access'.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import requests
from brightmatter.storage.database import Database

db = Database(); db.initialize()


# ── 1. AUTH PROBE ──
def _mint(cid, csec, rt):
    try:
        r = requests.post("https://oauth2.googleapis.com/token",
                          data={"client_id": cid, "client_secret": csec,
                                "refresh_token": rt, "grant_type": "refresh_token"}, timeout=20)
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def auth_probe() -> dict:
    out = {}
    # Google Ads token (expected: adwords scope only -> GA4 403)
    ads = _mint(os.getenv("GOOGLE_ADS_CLIENT_ID"), os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
                os.getenv("GOOGLE_ADS_REFRESH_TOKEN"))
    out["ads_token_scope"] = ads.get("scope", ads.get("error", "n/a"))
    if ads.get("access_token"):
        r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                         headers={"Authorization": f"Bearer {ads['access_token']}"}, timeout=20)
        out["ads_token_ga4_status"] = r.status_code
    # GA4 token (separate client; client creds may be absent here)
    g4 = _mint(os.getenv("GA4_CLIENT_ID") or os.getenv("GOOGLE_ADS_CLIENT_ID"),
               os.getenv("GA4_CLIENT_SECRET") or os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
               os.getenv("GA4_REFRESH_TOKEN"))
    out["ga4_token_mint"] = "ok" if g4.get("access_token") else g4.get("error", "n/a")
    out["ga4_property_id_known"] = bool(os.getenv("GA4_PROPERTY_ID"))
    if g4.get("access_token"):
        r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                         headers={"Authorization": f"Bearer {g4['access_token']}"}, timeout=20)
        out["ga4_token_admin_status"] = r.status_code
        if r.status_code == 200:
            summ = r.json().get("accountSummaries", [])
            out["ga4_properties_visible"] = sum(len(a.get("propertySummaries", [])) for a in summ)
    return out


# ── 2. DISCOVERY MAPPING (from existing data) ──
def discovery_mapping() -> dict:
    total = db.fetchone("SELECT count(DISTINCT account_id) FROM daily_metrics")[0]
    with_url = db.fetchone("""SELECT count(*) FROM accounts WHERE website_url IS NOT NULL AND website_url<>''
                              AND account_id IN (SELECT DISTINCT account_id FROM daily_metrics)""")[0]
    imported = db.fetchone("""SELECT count(DISTINCT account_id) FROM conversion_actions
        WHERE upper(category) LIKE '%IMPORT%' OR upper(action_type) LIKE '%ANALYT%'
           OR upper(action_name) LIKE '%GA4%' OR upper(action_name) LIKE '%ANALYTICS%'""")[0]
    ecom_funnel = db.fetchone("""SELECT count(DISTINCT account_id) FROM conversion_actions
        WHERE category IN ('ADD_TO_CART','BEGIN_CHECKOUT','PURCHASE')""")[0]
    ecom_full = db.fetchone("""SELECT count(DISTINCT account_id) FROM conversion_actions
        WHERE account_id IN (SELECT account_id FROM conversion_actions WHERE category='ADD_TO_CART')
          AND account_id IN (SELECT account_id FROM conversion_actions WHERE category='BEGIN_CHECKOUT')
          AND account_id IN (SELECT account_id FROM conversion_actions WHERE category='PURCHASE')""")[0]
    return {"active_accounts": total, "with_website_url": with_url,
            "imported_goal_linkage": imported, "ecommerce_any_funnel_event": ecom_funnel,
            "ecommerce_full_funnel_instrumented": ecom_full}


# ── 3. SIGNAL VALUE ──
def signal_value() -> dict:
    def cnt(t): return db.fetchone("SELECT count(*) FROM signals WHERE signal_type=?", [t])[0]
    cvr = cnt("cvr_drop") + cnt("cvr_change")
    cpa = cnt("cpa_spike") + cnt("cpa_change")
    return {
        "cvr_signals_LIKELY_capped": cvr,        # Signal 1 upgrade candidates
        "cpa_signals_LIKELY_capped": cpa,        # Signal 1 upgrade candidates
        "device_mobile_drag": cnt("device_mobile_drag"),   # Signal 2
        "weak_ad_strength": cnt("weak_ad_strength"),
        "total_signal1_addressable": cvr + cpa,
    }


print("[ga4-1] === AUTH PROBE ===")
for k, v in auth_probe().items():
    print(f"  {k}: {v}")
print("\n[ga4-1] === DISCOVERY MAPPING (from existing data) ===")
for k, v in discovery_mapping().items():
    print(f"  {k}: {v}")
print("\n[ga4-1] === SIGNAL VALUE (GA4-addressable BrightMatter signals) ===")
for k, v in signal_value().items():
    print(f"  {k}: {v}")
db.close()
print("\n[ga4-1] DONE")
