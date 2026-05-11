"""Pull ad-level final URLs for every account, aggregate the dominant non-Google
host per account, and UPDATE accounts.website_url.

READ-ONLY: uses brightmatter.ingestion.client.GoogleAdsClient which hard-blocks
every mutate path. All writes are to the local DuckDB only.

Strategy:
  - For each account in `accounts`, run AD_LANDING_PAGES (GAQL SELECT).
  - Extract every host from ad_group_ad.ad.final_urls.
  - Filter out Google's own redirect/tracking hosts.
  - The most-frequent host across the account's active ads becomes the canonical
    `accounts.website_url`.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.ingestion.queries import AD_LANDING_PAGES
from brightmatter.storage.database import Database

console = Console()

# Hosts to ignore — Google's redirect/tracking infra, ad networks, app stores.
_IGNORED_HOSTS = {
    "googleadservices.com",
    "www.googleadservices.com",
    "doubleclick.net",
    "www.doubleclick.net",
    "play.google.com",
    "apps.apple.com",
    "itunes.apple.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
}


def _normalize_host(url: str) -> str | None:
    """Return a normalized host (lowercased, www-stripped) or None to skip."""
    if not url:
        return None
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return None
    host = (p.netloc or p.path).lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if not host or host in _IGNORED_HOSTS or "." not in host:
        return None
    return host


def main() -> None:
    db = Database()
    db.initialize()

    accounts = db.fetchall("SELECT account_id, account_name FROM accounts ORDER BY account_name")
    console.print(f"\n[bold]Pulling landing-page URLs for {len(accounts)} accounts[/bold]")
    console.print("[dim]Read-only: GAQL SELECT only; no writes to Google Ads.[/dim]\n")

    client = GoogleAdsClient()

    updates: list[tuple[str, str]] = []
    errors = 0
    no_data = 0
    populated = 0

    with Progress(console=console) as progress:
        task = progress.add_task("Pulling URLs...", total=len(accounts))
        for aid, name in accounts:
            try:
                rows = client.query(aid, AD_LANDING_PAGES)
            except Exception:
                errors += 1
                progress.update(task, advance=1)
                continue

            host_counts: Counter[str] = Counter()
            for r in rows:
                urls = list(r.ad_group_ad.ad.final_urls or [])
                for u in urls:
                    h = _normalize_host(u)
                    if h:
                        host_counts[h] += 1

            if not host_counts:
                no_data += 1
                progress.update(task, advance=1)
                continue

            top_host, top_count = host_counts.most_common(1)[0]
            updates.append((aid, top_host))
            populated += 1
            progress.update(task, advance=1)

    console.print(f"\n[bold]Ingestion complete:[/bold] "
                  f"populated={populated}  no_ads={no_data}  errors={errors}\n")

    # Apply updates locally
    for aid, host in updates:
        db.execute("UPDATE accounts SET website_url = ? WHERE account_id = ?", [host, aid])

    # Summary of top domains
    table = Table(title="Top 30 hosts (across all accounts)", show_header=True, header_style="bold")
    table.add_column("Host", style="cyan")
    table.add_column("Accounts", justify="right")
    host_totals: Counter[str] = Counter(h for _, h in updates)
    for host, n in host_totals.most_common(30):
        table.add_row(host, str(n))
    console.print(table)
    db.close()


if __name__ == "__main__":
    main()
