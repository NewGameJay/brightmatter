"""Mint a GA4 OAuth refresh token (analytics.readonly) — for GA4 Phase 2 access.

Opens a browser; sign in as the Google account that has GA4 access
(info@hawkemedia.com). Verifies the token against the GA4 Admin API on the spot and
lists the properties it can see, then prints the refresh token to paste into .env.

Read-only: mints a credential and does one list call. Pulls no GA4 report data.

Run interactively (browser opens on your machine):
    python scripts/ga4_oauth.py

Uses GA4_CLIENT_ID/SECRET if set, else falls back to the Google Ads OAuth client.
NOTE: the resulting refresh token only works with the SAME client_id/secret it was
minted under — the script prints which client it used so you pair them correctly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
LOGIN_HINT = "info@hawkemedia.com"


def main() -> int:
    # Prefer a dedicated GA4 OAuth client if present; else reuse the Ads client app.
    client_id = (os.environ.get("GA4_CLIENT_ID") or os.environ.get("GOOGLE_ADS_CLIENT_ID", "")).strip()
    client_secret = (os.environ.get("GA4_CLIENT_SECRET") or os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")).strip()
    used = "GA4_CLIENT_ID" if os.environ.get("GA4_CLIENT_ID") else "GOOGLE_ADS_CLIENT_ID (fallback)"
    if not client_id or not client_secret:
        print("ERROR: no OAuth client creds in .env (need GA4_CLIENT_ID/SECRET or "
              "GOOGLE_ADS_CLIENT_ID/SECRET).", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }},
        scopes=SCOPES,
    )

    print(f"OAuth client: {used}")
    print(f"Opening browser — sign in as {LOGIN_HINT} (the account with GA4 access).")
    creds = flow.run_local_server(
        port=0, prompt="consent", access_type="offline",
        login_hint=LOGIN_HINT, open_browser=True,
    )
    if not creds.refresh_token:
        print("ERROR: no refresh token returned. Revoke at "
              "https://myaccount.google.com/permissions and re-run.", file=sys.stderr)
        return 2

    # ── verify on the spot ──
    print("\nVerifying token against GA4 Admin API...")
    r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                     headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    if r.status_code == 200:
        summ = r.json().get("accountSummaries", [])
        props = [p for a in summ for p in a.get("propertySummaries", [])]
        print(f"  SUCCESS — {len(summ)} GA4 account(s), {len(props)} property(ies) visible:")
        for p in props[:15]:
            print(f"    {p.get('displayName')}  ({p.get('property')})")
        if len(props) > 15:
            print(f"    ... +{len(props)-15} more")
    elif r.status_code == 403 and "SERVICE_DISABLED" in r.text:
        print("  TOKEN OK, but the Analytics Admin API is NOT enabled on this OAuth "
              "client's Google Cloud project. Enable 'Google Analytics Admin API' there, then re-run.")
    else:
        print(f"  API check returned {r.status_code}: {r.text[:300]}")

    print("\n" + "=" * 64)
    print("GA4 REFRESH TOKEN — paste into .env as GA4_REFRESH_TOKEN:")
    print()
    print(creds.refresh_token)
    print()
    print(f"(minted under client: {used} — keep that client_id/secret as the GA4 pair)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
