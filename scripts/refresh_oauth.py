"""Refresh the Google Ads OAuth refresh token.

Opens a browser, you sign in with the Google account that has MCC access,
and prints a new refresh token. Paste it into .env as GOOGLE_ADS_REFRESH_TOKEN.

Read-only: this only mints a credential. It does not touch any Google Ads data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> int:
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("ERROR: GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET not set in .env",
              file=sys.stderr)
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

    print("Opening browser for Google sign-in...")
    print("Use the Google account that has MCC access for the Hawke Media Google Ads account.")
    creds = flow.run_local_server(
        port=0,
        prompt="consent",        # force re-consent so we always get a refresh token
        access_type="offline",   # ensure refresh token is issued
        open_browser=True,
    )

    if not creds.refresh_token:
        print("ERROR: Google did not return a refresh token. "
              "Try revoking access at https://myaccount.google.com/permissions and re-run.",
              file=sys.stderr)
        return 2

    print()
    print("=" * 60)
    print("NEW REFRESH TOKEN (paste into .env, replacing GOOGLE_ADS_REFRESH_TOKEN):")
    print()
    print(creds.refresh_token)
    print()
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
