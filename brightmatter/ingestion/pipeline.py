"""Ingestion pipeline — orchestrates data pulls across all accounts.

Supports three modes:
  - live: pulls from Google Ads API
  - demo: generates sample data for development/testing
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from brightmatter.config import google_ads
from brightmatter.ingestion import queries
from brightmatter.ingestion.normalizer import (
    normalize_account,
    normalize_change_event,
    normalize_daily_metrics,
    normalize_keyword_metrics,
)
from brightmatter.models.account import Account, BusinessType, SpendTier
from brightmatter.models.changes import ChangeActor, ChangeEvent
from brightmatter.models.metrics import DailyMetrics, KeywordMetrics
from brightmatter.storage.repository import Repository

logger = logging.getLogger("brightmatter.ingestion")


class IngestionPipeline:
    """Pulls data from Google Ads accounts and stores it in DuckDB."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from brightmatter.ingestion.client import GoogleAdsClient
            self._client = GoogleAdsClient()
        return self._client

    @property
    def is_live(self) -> bool:
        return google_ads.is_configured

    # ── Public API ──

    def discover_accounts(self) -> list[Account]:
        """Discover and store all accessible accounts from the MCC."""
        if not self.is_live:
            logger.info("No API credentials — using demo accounts")
            return self._demo_discover_accounts()

        raw_accounts = self.client.list_accessible_accounts()
        logger.info("Discovered %d accounts from MCC %s", len(raw_accounts), self.client.login_customer_id)

        accounts = []
        for raw in raw_accounts:
            account = normalize_account(raw, self.client.login_customer_id)
            self.repo.upsert_account(account)
            accounts.append(account)
        return accounts

    def ingest_daily(self, account_ids: list[str] | None = None, days: int = 30) -> dict[str, int]:
        """Tier 1: Pull daily campaign metrics for all (or specified) accounts."""
        accounts = self._resolve_accounts(account_ids)
        if not accounts:
            logger.warning("No accounts to ingest")
            return {}

        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        results = {}

        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_daily_live(account.account_id, start_date, end_date)
                else:
                    count = self._ingest_daily_demo(account, start_date, end_date)
                results[account.account_id] = count
                logger.info("Ingested %d daily metric rows for %s (%s)", count, account.account_name, account.account_id)
            except Exception:
                logger.exception("Failed to ingest daily metrics for %s", account.account_id)
                results[account.account_id] = 0
        return results

    def ingest_keywords(self, account_ids: list[str] | None = None, days: int = 7) -> dict[str, int]:
        """Tier 2: Pull keyword Quality Score data."""
        accounts = self._resolve_accounts(account_ids)
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        results = {}

        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_keywords_live(account.account_id, start_date, end_date)
                else:
                    count = self._ingest_keywords_demo(account, start_date)
                results[account.account_id] = count
                logger.info("Ingested %d keyword rows for %s", count, account.account_id)
            except Exception:
                logger.exception("Failed to ingest keywords for %s", account.account_id)
                results[account.account_id] = 0
        return results

    def ingest_changes(self, account_ids: list[str] | None = None, days: int = 30) -> dict[str, int]:
        """Tier 3: Pull change history events. API limit: 30 days max."""
        accounts = self._resolve_accounts(account_ids)
        capped_days = min(days, 30)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=capped_days)
        results = {}

        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_changes_live(account.account_id, start_date, end_date)
                else:
                    count = self._ingest_changes_demo(account)
                results[account.account_id] = count
                logger.info("Ingested %d change events for %s", count, account.account_id)
            except Exception:
                logger.exception("Failed to ingest changes for %s", account.account_id)
                results[account.account_id] = 0
        return results

    def ingest_conversion_actions(self, account_ids: list[str] | None = None) -> dict[str, int]:
        """Pull conversion action configuration for all accounts."""
        accounts = self._resolve_accounts(account_ids)
        results = {}
        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_conversion_actions_live(account.account_id)
                else:
                    count = 0
                results[account.account_id] = count
                logger.info("Ingested %d conversion actions for %s", count, account.account_id)
            except Exception:
                logger.exception("Failed to ingest conversion actions for %s", account.account_id)
                results[account.account_id] = 0
        return results

    def ingest_assets(self, account_ids: list[str] | None = None) -> dict[str, int]:
        """Pull extension/asset coverage per campaign."""
        accounts = self._resolve_accounts(account_ids)
        results = {}
        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_assets_live(account.account_id)
                else:
                    count = 0
                results[account.account_id] = count
            except Exception:
                logger.exception("Failed to ingest assets for %s", account.account_id)
                results[account.account_id] = 0
        return results

    def classify_accounts(self) -> int:
        """Infer business type and vertical from campaign names, conversion actions, campaign types."""
        accounts = self.repo.list_accounts()
        classified = 0
        for account in accounts:
            btype, vertical = self._classify_account(account.account_id)
            if btype != "unknown":
                self.repo.db.execute(
                    "UPDATE accounts SET business_type = ?, vertical = ? WHERE account_id = ?",
                    [btype, vertical, account.account_id],
                )
                classified += 1
        logger.info("Classified %d/%d accounts", classified, len(accounts))
        return classified

    def _classify_account(self, account_id: str) -> tuple[str, str]:
        """Classify an account via brightmatter.ingestion.classifier.

        The previous bare-substring heuristic produced widely-wrong results
        (e.g. `competitor` → pets, `MCAT` → pets, `AddToCart` → automotive).
        The new classifier uses word-boundary regex, account-name as primary
        signal, and conversion-category counts for business_type.
        """
        from brightmatter.ingestion.classifier import (
            ClassificationInputs,
            classify,
        )

        acct = self.repo.db.fetchone(
            "SELECT account_name, website_url FROM accounts WHERE account_id = ?",
            [account_id],
        )
        account_name = (acct[0] if acct else "") or ""
        website_url = (acct[1] if acct else "") or ""

        # Optional: fetched website title/description (from account_web_meta).
        # Missing rows are fine — the classifier handles empty inputs.
        web_meta = self.repo.db.fetchone(
            "SELECT title, description FROM account_web_meta WHERE account_id = ?",
            [account_id],
        )
        title_text = (web_meta[0] if web_meta else "") or ""
        description_text = (web_meta[1] if web_meta else "") or ""

        conv_rows = self.repo.db.fetchall(
            "SELECT action_name, category FROM conversion_actions WHERE account_id = ? AND status = 'ENABLED'",
            [account_id],
        )
        conversions = [((r[0] or ""), (r[1] or "")) for r in conv_rows]

        camp_rows = self.repo.db.fetchall(
            "SELECT DISTINCT campaign_name FROM daily_metrics WHERE account_id = ? AND status = 'ENABLED'",
            [account_id],
        )
        campaign_names = [(r[0] or "") for r in camp_rows]

        type_rows = self.repo.db.fetchall(
            "SELECT campaign_type, count(*) FROM daily_metrics WHERE account_id = ? GROUP BY campaign_type",
            [account_id],
        )
        campaign_types = {(r[0] or "UNKNOWN"): r[1] for r in type_rows}

        result = classify(ClassificationInputs(
            account_id=account_id,
            account_name=account_name,
            website_url=website_url,
            title_text=title_text,
            description_text=description_text,
            campaign_names=campaign_names,
            campaign_types=campaign_types,
            conversions=conversions,
        ))
        return result.business_type.value, result.vertical

    def ingest_keyword_counts(self, account_ids: list[str] | None = None) -> dict[str, int]:
        """Pull keyword + negative keyword counts per campaign."""
        accounts = self._resolve_accounts(account_ids)
        results = {}
        for account in accounts:
            try:
                if self.is_live:
                    count = self._ingest_keyword_counts_live(account.account_id)
                else:
                    count = 0
                results[account.account_id] = count
                logger.info("Ingested %d keyword count rows for %s", count, account.account_id)
            except Exception:
                logger.exception("Failed to ingest keyword counts for %s", account.account_id)
                results[account.account_id] = 0
        return results

    # ── Live ingestion ──

    def _ingest_assets_live(self, account_id: str) -> int:
        from collections import defaultdict
        try:
            rows = self.client.query(account_id, queries.CAMPAIGN_ASSETS)
        except Exception:
            logger.warning("Could not pull assets for %s", account_id)
            return 0
        campaign_types = defaultdict(lambda: defaultdict(int))
        for r in rows:
            cid = str(r.campaign.id)
            atype = r.asset.type_.name if hasattr(r.asset.type_, 'name') else str(r.asset.type_)
            campaign_types[cid][atype] += 1

        count = 0
        for cid, types in campaign_types.items():
            for atype, cnt in types.items():
                self.repo.db.execute(
                    """INSERT OR REPLACE INTO asset_coverage VALUES (?, ?, ?, ?, current_timestamp)""",
                    (account_id, cid, atype, cnt),
                )
                count += 1
        return count

    def _ingest_keyword_counts_live(self, account_id: str) -> int:
        from collections import defaultdict
        campaign_data = defaultdict(lambda: {"name": "", "keyword_count": 0,
                                              "broad_count": 0, "phrase_count": 0,
                                              "exact_count": 0, "negative_count": 0})

        try:
            active_rows = self.client.query(account_id, queries.ACTIVE_KEYWORDS)
            seen_kw = set()
            for r in active_rows:
                cid = str(r.campaign.id)
                kw_key = (cid, r.ad_group_criterion.keyword.text)
                if kw_key in seen_kw:
                    continue
                seen_kw.add(kw_key)
                campaign_data[cid]["name"] = r.campaign.name
                campaign_data[cid]["keyword_count"] += 1
                mt = r.ad_group_criterion.keyword.match_type.name if hasattr(r.ad_group_criterion.keyword.match_type, 'name') else str(r.ad_group_criterion.keyword.match_type)
                if mt == "BROAD":
                    campaign_data[cid]["broad_count"] += 1
                elif mt == "PHRASE":
                    campaign_data[cid]["phrase_count"] += 1
                elif mt == "EXACT":
                    campaign_data[cid]["exact_count"] += 1
        except Exception:
            logger.warning("Could not pull active keywords for %s", account_id)

        try:
            neg_rows = self.client.query(account_id, queries.NEGATIVE_KEYWORDS)
            for r in neg_rows:
                cid = str(r.campaign.id)
                campaign_data[cid]["name"] = campaign_data[cid]["name"] or r.campaign.name
                campaign_data[cid]["negative_count"] += 1
        except Exception:
            logger.warning("Could not pull negative keywords for %s", account_id)

        for cid, d in campaign_data.items():
            self.repo.db.execute(
                """INSERT OR REPLACE INTO keyword_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
                (account_id, cid, d["name"], d["keyword_count"],
                 d["broad_count"], d["phrase_count"],
                 d["exact_count"], d["negative_count"]),
            )
        return len(campaign_data)

    def _ingest_conversion_actions_live(self, account_id: str) -> int:
        gaql = queries.CONVERSION_ACTIONS
        rows = self.client.query(account_id, gaql)
        count = 0
        for r in rows:
            ca = r.conversion_action
            self.repo.db.execute(
                """INSERT OR REPLACE INTO conversion_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
                (
                    account_id, str(ca.id), ca.name,
                    ca.status.name if hasattr(ca.status, 'name') else str(ca.status),
                    ca.type_.name if hasattr(ca.type_, 'name') else str(ca.type_),
                    ca.category.name if hasattr(ca.category, 'name') else str(ca.category),
                    bool(ca.primary_for_goal),
                    ca.counting_type.name if hasattr(ca.counting_type, 'name') else str(ca.counting_type),
                    ca.attribution_model_settings.attribution_model.name
                        if hasattr(ca.attribution_model_settings.attribution_model, 'name')
                        else str(ca.attribution_model_settings.attribution_model),
                ),
            )
            count += 1
        return count

    def _ingest_daily_live(self, account_id: str, start_date: date, end_date: date) -> int:
        gaql = queries.DAILY_CAMPAIGN_METRICS.format(start_date=start_date, end_date=end_date)
        rows = self.client.query(account_id, gaql)
        metrics = [normalize_daily_metrics(r, account_id) for r in rows]
        return self.repo.insert_daily_metrics(metrics)

    def _ingest_keywords_live(self, account_id: str, start_date: date, end_date: date) -> int:
        gaql = queries.KEYWORD_QUALITY_SCORES.format(start_date=start_date, end_date=end_date)
        rows = self.client.query(account_id, gaql)
        metrics = [normalize_keyword_metrics(r, account_id, start_date) for r in rows]
        return self.repo.insert_keyword_metrics(metrics)

    def _ingest_changes_live(self, account_id: str, start: datetime, end: datetime) -> int:
        gaql = queries.CHANGE_EVENTS.format(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        rows = self.client.query(account_id, gaql)
        events = [normalize_change_event(r, account_id) for r in rows]
        return self.repo.insert_change_events(events)

    # ── Demo data generation ──

    def _resolve_accounts(self, account_ids: list[str] | None) -> list[Account]:
        if account_ids:
            return [a for a in self.repo.list_accounts() if a.account_id in account_ids]
        return self.repo.list_accounts()

    def _demo_discover_accounts(self) -> list[Account]:
        """Generate 20 realistic demo accounts across verticals."""
        demo_accounts = [
            ("1001", "Luxe Skincare Co", BusinessType.ECOMMERCE, "skincare", SpendTier.MID),
            ("1002", "Metro Dental Group", BusinessType.LOCAL, "dental", SpendTier.SMALL),
            ("1003", "CloudStack SaaS", BusinessType.SAAS, "software", SpendTier.LARGE),
            ("1004", "FreshFit Supplements", BusinessType.ECOMMERCE, "supplements", SpendTier.MID),
            ("1005", "Premier Law Partners", BusinessType.LEAD_GEN, "legal", SpendTier.LARGE),
            ("1006", "HomeGlow Candles", BusinessType.ECOMMERCE, "home_goods", SpendTier.SMALL),
            ("1007", "TechRecruit Pro", BusinessType.B2B, "recruiting", SpendTier.MID),
            ("1008", "Sunrise Solar", BusinessType.LEAD_GEN, "solar", SpendTier.MID),
            ("1009", "PetPals Online", BusinessType.ECOMMERCE, "pets", SpendTier.SMALL),
            ("1010", "EliteFit Gym", BusinessType.LOCAL, "fitness", SpendTier.MICRO),
            ("1011", "Verdant Gardens", BusinessType.ECOMMERCE, "garden", SpendTier.SMALL),
            ("1012", "SwiftShip Logistics", BusinessType.B2B, "logistics", SpendTier.LARGE),
            ("1013", "BrightSmile Ortho", BusinessType.LOCAL, "dental", SpendTier.MID),
            ("1014", "NovaTech Consulting", BusinessType.B2B, "consulting", SpendTier.MID),
            ("1015", "PureGlow Beauty", BusinessType.ECOMMERCE, "beauty", SpendTier.MID),
            ("1016", "SafeHaven Insurance", BusinessType.LEAD_GEN, "insurance", SpendTier.LARGE),
            ("1017", "WildTrail Outdoor", BusinessType.ECOMMERCE, "outdoor", SpendTier.SMALL),
            ("1018", "DataPulse Analytics", BusinessType.SAAS, "analytics", SpendTier.MID),
            ("1019", "GreenLeaf HVAC", BusinessType.LOCAL, "hvac", SpendTier.SMALL),
            ("1020", "Artisan Coffee Co", BusinessType.ECOMMERCE, "food_beverage", SpendTier.MICRO),
        ]
        accounts = []
        for aid, name, btype, vertical, tier in demo_accounts:
            account = Account(
                account_id=aid, account_name=name, mcc_id="demo-mcc",
                business_type=btype, vertical=vertical, spend_tier=tier,
                website_url=f"https://{name.lower().replace(' ', '')}.com",
                first_seen=date.today() - timedelta(days=random.randint(90, 365)),
                last_updated=datetime.now(timezone.utc),
            )
            self.repo.upsert_account(account)
            accounts.append(account)
        return accounts

    def _ingest_daily_demo(self, account: Account, start_date: date, end_date: date) -> int:
        """Generate realistic daily metrics for a demo account."""
        campaign_templates = _demo_campaigns_for(account)
        metrics = []
        d = start_date
        while d <= end_date:
            for ct in campaign_templates:
                base_impr = ct["base_impressions"]
                dow_mult = 1.1 if d.weekday() < 5 else 0.8
                noise = random.uniform(0.85, 1.15)
                impr = int(base_impr * dow_mult * noise)
                ctr = ct["base_ctr"] * random.uniform(0.9, 1.1)
                clicks = max(1, int(impr * ctr))
                avg_cpc = ct["base_cpc"] * random.uniform(0.85, 1.15)
                cost_micros = int(clicks * avg_cpc * 1_000_000)
                cvr = ct["base_cvr"] * random.uniform(0.8, 1.2)
                conversions = round(clicks * cvr, 2)
                avg_conv_value = ct.get("avg_conv_value", 0)
                conv_value = round(conversions * avg_conv_value * random.uniform(0.9, 1.1), 2)

                metrics.append(DailyMetrics(
                    account_id=account.account_id,
                    campaign_id=ct["id"],
                    campaign_name=ct["name"],
                    campaign_type=ct["type"],
                    date=d,
                    impressions=impr,
                    clicks=clicks,
                    cost_micros=cost_micros,
                    conversions=conversions,
                    conversion_value=conv_value,
                    search_impression_share=random.uniform(0.3, 0.9) if ct["type"] == "SEARCH" else None,
                    search_budget_lost_is=random.uniform(0.0, 0.2) if ct["type"] == "SEARCH" else None,
                    search_rank_lost_is=random.uniform(0.05, 0.3) if ct["type"] == "SEARCH" else None,
                    bidding_strategy=ct["bidding"],
                    daily_budget_micros=ct["budget_micros"],
                    status="ENABLED",
                ))
            d += timedelta(days=1)
        return self.repo.insert_daily_metrics(metrics)

    def _ingest_keywords_demo(self, account: Account, week_start: date) -> int:
        """Generate keyword QS data for demo account."""
        kw_templates = [
            ("kw1", "brand name", "EXACT", 8), ("kw2", "buy product", "BROAD", 5),
            ("kw3", "best service near me", "PHRASE", 6), ("kw4", "product reviews", "BROAD", 4),
            ("kw5", "competitor name", "EXACT", 3), ("kw6", "category product", "PHRASE", 7),
        ]
        qs_labels = ["ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE"]
        metrics = []
        for kid, text, match, base_qs in kw_templates:
            qs = max(1, min(10, base_qs + random.randint(-1, 1)))
            metrics.append(KeywordMetrics(
                account_id=account.account_id, campaign_id="c1",
                ad_group_id="ag1", keyword_id=kid,
                keyword_text=text, match_type=match, week_start=week_start,
                quality_score=qs,
                expected_ctr=random.choice(qs_labels),
                ad_relevance=random.choice(qs_labels),
                landing_page_experience=random.choice(qs_labels),
                impressions=random.randint(100, 5000),
                clicks=random.randint(10, 500),
                cost_micros=random.randint(5_000_000, 50_000_000),
                conversions=round(random.uniform(0, 20), 1),
            ))
        return self.repo.insert_keyword_metrics(metrics)

    def _ingest_changes_demo(self, account: Account) -> int:
        """Generate some demo change events."""
        change_types = [
            ("BUDGET_CHANGE", "campaign_budget", "Budget updated"),
            ("BID_CHANGE", "campaign", "Bidding strategy changed"),
            ("KEYWORD_ADD", "ad_group_criterion", "Keyword added"),
            ("STATUS_CHANGE", "campaign", "Campaign paused"),
            ("AD_CHANGE", "ad_group_ad", "RSA updated"),
        ]
        events = []
        for i in range(random.randint(3, 12)):
            ct = random.choice(change_types)
            is_auto = random.random() < 0.2
            events.append(ChangeEvent(
                account_id=account.account_id,
                change_id=uuid.uuid4().hex[:16],
                change_timestamp=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90)),
                change_type=ct[0],
                resource_type=ct[1],
                resource_name=f"customers/{account.account_id}/{ct[1]}s/123",
                campaign_id="c1",
                actor=ChangeActor.AUTO_APPLIED if is_auto else ChangeActor.HUMAN,
                actor_email="" if is_auto else "manager@agency.com",
                old_value=f"old_{ct[2]}",
                new_value=f"new_{ct[2]}",
            ))
        return self.repo.insert_change_events(events)


def _demo_campaigns_for(account: Account) -> list[dict[str, Any]]:
    """Generate campaign templates based on account business type."""
    spend_mult = {"<5k": 0.3, "5k-25k": 1.0, "25k-100k": 3.0, "100k+": 8.0}
    mult = spend_mult.get(account.spend_tier.value, 1.0)

    campaigns = [
        {"id": "c1", "name": f"{account.account_name} - Brand Search",
         "type": "SEARCH", "bidding": "MAXIMIZE_CONVERSIONS",
         "base_impressions": int(2000 * mult), "base_ctr": 0.08,
         "base_cpc": 1.50, "base_cvr": 0.15, "avg_conv_value": 80,
         "budget_micros": int(100 * mult * 1_000_000)},
        {"id": "c2", "name": f"{account.account_name} - Non-Brand Search",
         "type": "SEARCH", "bidding": "TARGET_CPA",
         "base_impressions": int(5000 * mult), "base_ctr": 0.035,
         "base_cpc": 4.50, "base_cvr": 0.03, "avg_conv_value": 120,
         "budget_micros": int(200 * mult * 1_000_000)},
        {"id": "c3", "name": f"{account.account_name} - PMax",
         "type": "PERFORMANCE_MAX", "bidding": "MAXIMIZE_CONVERSION_VALUE",
         "base_impressions": int(8000 * mult), "base_ctr": 0.02,
         "base_cpc": 2.00, "base_cvr": 0.025, "avg_conv_value": 100,
         "budget_micros": int(250 * mult * 1_000_000)},
    ]

    if account.business_type.value == "ecommerce":
        campaigns.append({
            "id": "c4", "name": f"{account.account_name} - Shopping",
            "type": "SHOPPING", "bidding": "TARGET_ROAS",
            "base_impressions": int(6000 * mult), "base_ctr": 0.015,
            "base_cpc": 0.80, "base_cvr": 0.02, "avg_conv_value": 65,
            "budget_micros": int(150 * mult * 1_000_000),
        })

    return campaigns
