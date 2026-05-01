"""Central configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RESEARCH_DIR = ROOT_DIR / "research"

DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "brightmatter.duckdb"


class GoogleAdsConfig:
    developer_token: str = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    client_id: str = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
    client_secret: str = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
    refresh_token: str = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
    login_customer_id: str = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")
    service_account_path: str = os.getenv("GOOGLE_ADS_SERVICE_ACCOUNT_PATH", "")
    impersonated_email: str = os.getenv("GOOGLE_ADS_IMPERSONATED_EMAIL", "")

    @property
    def has_oauth2(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    @property
    def has_service_account(self) -> bool:
        return bool(self.service_account_path and os.path.exists(self.service_account_path))

    @property
    def use_service_account(self) -> bool:
        return self.has_service_account and not self.has_oauth2

    @property
    def is_configured(self) -> bool:
        return bool(self.developer_token and self.login_customer_id and (self.has_oauth2 or self.has_service_account))


class AnthropicConfig:
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


google_ads = GoogleAdsConfig()
anthropic = AnthropicConfig()
