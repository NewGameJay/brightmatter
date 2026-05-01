"""Google Ads API client — READ-ONLY MCC traversal and GAQL execution.

CRITICAL SAFETY CONSTRAINT:
    BrightMatter is a READ-ONLY system. It MUST NEVER write to, modify, or
    mutate any external platform (Google Ads, Merchant Center, or any other).
    This client exposes ONLY the SearchStream read path. All mutate services
    (CampaignService, AdGroupService, etc.) are deliberately inaccessible.
    Any attempt to obtain a mutate service will raise a hard error.
"""

from __future__ import annotations

import logging
from typing import Any

from google.ads.googleads.client import GoogleAdsClient as _GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from brightmatter.config import google_ads
from brightmatter.ingestion.queries import ACCESSIBLE_ACCOUNTS, ACCOUNT_INFO

logger = logging.getLogger("brightmatter.ingestion")

_BLOCKED_SERVICES = frozenset({
    "CampaignService", "AdGroupService", "AdGroupAdService",
    "AdGroupCriterionService", "CampaignBudgetService",
    "CampaignCriterionService", "BiddingStrategyService",
    "ConversionActionService", "CustomerService",
    "CampaignAssetService", "AssetService", "AssetGroupService",
    "ExtensionFeedItemService", "FeedService", "FeedItemService",
    "LabelService", "CampaignLabelService", "SharedSetService",
    "SharedCriterionService", "CampaignSharedSetService",
    "RemarketingActionService", "UserListService",
    "ConversionCustomVariableService", "CustomerExtensionSettingService",
    "CampaignExtensionSettingService", "AdGroupExtensionSettingService",
    "BatchJobService", "OfflineUserDataJobService",
    "RecommendationService", "ApplyRecommendationRequest",
})

_BLOCKED_GAQL = frozenset({"INSERT", "UPDATE", "DELETE", "CREATE", "REMOVE"})


class PlatformWriteBlockedError(RuntimeError):
    """Raised when any code path attempts to write to an external platform."""


class GoogleAdsClient:
    """READ-ONLY Google Ads API client.

    This client can ONLY execute GAQL SELECT queries via SearchStream.
    All mutate/write operations are blocked at the architecture level.
    """

    def __init__(self):
        if not google_ads.is_configured:
            raise RuntimeError(
                "Google Ads API not configured. Set GOOGLE_ADS_DEVELOPER_TOKEN, "
                "GOOGLE_ADS_LOGIN_CUSTOMER_ID, and either OAuth2 credentials or "
                "GOOGLE_ADS_SERVICE_ACCOUNT_PATH in .env"
            )

        if google_ads.use_service_account:
            logger.info("Using service account auth: %s", google_ads.service_account_path)
            from google.oauth2 import service_account as sa_mod
            scopes = ["https://www.googleapis.com/auth/adwords"]
            creds = sa_mod.Credentials.from_service_account_file(
                google_ads.service_account_path, scopes=scopes,
            )
            if google_ads.impersonated_email:
                creds = creds.with_subject(google_ads.impersonated_email)
            self._client = _GoogleAdsClient(
                credentials=creds,
                developer_token=google_ads.developer_token,
                login_customer_id=google_ads.login_customer_id or None,
            )
        else:
            logger.info("Using OAuth2 auth")
            self._client = _GoogleAdsClient.load_from_dict({
                "developer_token": google_ads.developer_token,
                "client_id": google_ads.client_id,
                "client_secret": google_ads.client_secret,
                "refresh_token": google_ads.refresh_token,
                "login_customer_id": google_ads.login_customer_id,
                "use_proto_plus": True,
            })

        self._ga_service = self._client.get_service("GoogleAdsService")

    def get_service(self, service_name: str):
        """BLOCKED — BrightMatter is read-only. No platform services are exposed."""
        if service_name in _BLOCKED_SERVICES or service_name != "GoogleAdsService":
            raise PlatformWriteBlockedError(
                f"BLOCKED: BrightMatter is READ-ONLY. "
                f"Access to '{service_name}' is forbidden. "
                f"This system must never write to external platforms."
            )
        return self._ga_service

    @property
    def login_customer_id(self) -> str:
        return google_ads.login_customer_id

    def query(self, customer_id: str, gaql: str) -> list[Any]:
        """Execute a read-only GAQL SELECT query via SearchStream."""
        gaql_upper = gaql.strip().upper()
        for keyword in _BLOCKED_GAQL:
            if gaql_upper.startswith(keyword):
                raise PlatformWriteBlockedError(
                    f"BLOCKED: GAQL '{keyword}' operations are forbidden. "
                    f"BrightMatter is READ-ONLY."
                )

        rows = []
        try:
            stream = self._ga_service.search_stream(customer_id=customer_id, query=gaql)
            for batch in stream:
                for row in batch.results:
                    rows.append(row)
        except GoogleAdsException as ex:
            logger.error(
                "Google Ads API error for customer %s: %s",
                customer_id, ex.failure.errors[0].message if ex.failure.errors else str(ex),
            )
            raise
        return rows

    def list_accessible_accounts(self) -> list[dict[str, Any]]:
        """List all child accounts accessible from the MCC."""
        rows = self.query(self.login_customer_id, ACCESSIBLE_ACCOUNTS)
        accounts = []
        for row in rows:
            cc = row.customer_client
            accounts.append({
                "id": str(cc.id),
                "name": cc.descriptive_name,
                "currency_code": cc.currency_code,
                "manager": cc.manager,
                "status": cc.status.name,
            })
        return accounts

    def get_account_info(self, customer_id: str) -> dict[str, Any]:
        """Get basic info for a single account."""
        rows = self.query(customer_id, ACCOUNT_INFO)
        if not rows:
            return {}
        c = rows[0].customer
        return {
            "id": str(c.id),
            "name": c.descriptive_name,
            "currency_code": c.currency_code,
            "manager": c.manager,
        }

    def mutate(self, *args, **kwargs):
        """BLOCKED — hard error on any mutate attempt."""
        raise PlatformWriteBlockedError(
            "BLOCKED: mutate() is forbidden. BrightMatter is READ-ONLY."
        )
