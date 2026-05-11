"""Fetch <title> and meta tags for every account with a known website_url.

Stores results in `account_web_meta`. Read-only with respect to Google Ads;
this only makes HTTPS GETs to the advertisers' own public websites.

Strategy:
  - Concurrent GETs via httpx (HTTP/2-capable, follows redirects).
  - 10s timeout, browser-like User-Agent.
  - Parse <title>, <meta name="description">, og:title, og:description.
  - UPSERT into account_web_meta with status_code / error captured.

Re-runnable: existing entries are overwritten.
"""

from __future__ import annotations

import concurrent.futures
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import lxml.html
from rich.console import Console
from rich.progress import Progress

from brightmatter.storage.database import Database

console = Console()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

TIMEOUT = httpx.Timeout(connect=8.0, read=10.0, write=8.0, pool=None)
MAX_WORKERS = 16  # concurrent fetches


def _fetch_one(account_id: str, host: str) -> dict:
    """Return {account_id, title, description, status_code, error} for one host."""
    out = {"account_id": account_id, "title": None, "description": None,
           "status_code": None, "error": None}
    url = host if host.startswith("http") else f"https://{host}/"
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": UA}) as client:
            r = client.get(url)
            out["status_code"] = r.status_code
            if r.status_code >= 400:
                out["error"] = f"HTTP {r.status_code}"
                return out
            html = r.text
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return out

    try:
        doc = lxml.html.fromstring(html)
    except Exception as e:
        out["error"] = f"parse: {type(e).__name__}: {str(e)[:80]}"
        return out

    # Pull title (prefer og:title if present, more semantic)
    title = None
    for og in doc.xpath('//meta[@property="og:title"]/@content'):
        if og and og.strip():
            title = og.strip()
            break
    if not title:
        t = doc.xpath("//title/text()")
        if t and t[0].strip():
            title = t[0].strip()
    out["title"] = (title or "")[:500]

    # Pull description (og:description or meta[description])
    description = None
    for og in doc.xpath('//meta[@property="og:description"]/@content'):
        if og and og.strip():
            description = og.strip()
            break
    if not description:
        for m in doc.xpath('//meta[@name="description"]/@content'):
            if m and m.strip():
                description = m.strip()
                break
    out["description"] = (description or "")[:1000]
    return out


def main() -> None:
    db = Database()
    db.initialize()

    rows = db.fetchall(
        "SELECT account_id, website_url FROM accounts "
        "WHERE website_url IS NOT NULL AND website_url != '' "
        "ORDER BY account_name"
    )
    console.print(f"\n[bold]Fetching website titles for {len(rows)} accounts[/bold]")
    console.print("[dim]Read-only HTTPS GETs to advertiser websites; no writes to Google Ads.[/dim]\n")

    results: list[dict] = []
    with Progress(console=console) as progress:
        task = progress.add_task("Fetching...", total=len(rows))
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            future_map = {ex.submit(_fetch_one, aid, host): (aid, host) for aid, host in rows}
            for fut in concurrent.futures.as_completed(future_map):
                results.append(fut.result())
                progress.update(task, advance=1)

    # Persist
    ok = 0
    err = 0
    for r in results:
        db.execute(
            """
            INSERT OR REPLACE INTO account_web_meta (account_id, title, description, status_code, error, fetched_at)
            VALUES (?, ?, ?, ?, ?, current_timestamp)
            """,
            [r["account_id"], r["title"], r["description"], r["status_code"], r["error"]],
        )
        if r["title"] or r["description"]:
            ok += 1
        else:
            err += 1

    console.print(f"\n[bold]Done.[/bold] Got title or description for [green]{ok}[/] accounts; [yellow]{err}[/] failed.")
    db.close()


if __name__ == "__main__":
    main()
