"""Runtime/environment configuration.

This module holds *technical* configuration only (ports, paths, provider
selection). Provisional *business* assumptions live in
``dynamic_pricing.pricing.defaults`` and in the persisted PricingConfiguration row.
Keeping the two apart is deliberate: business rules must be changeable by an
operator at runtime, environment settings must not.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings:
    """Environment-driven settings. Plain class: no magic, easy to read."""

    def __init__(self) -> None:
        self.data_provider: str = os.getenv("DATA_PROVIDER", "mock").strip().lower()
        self.market_provider: str = os.getenv("MARKET_PROVIDER", "mock").strip().lower()

        default_db = REPO_ROOT / "data" / "dynamic_pricing.db"
        self.database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{default_db}")

        self.api_host: str = os.getenv("API_HOST", "127.0.0.1")
        self.api_port: int = int(os.getenv("API_PORT", "8000"))
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",")
            if o.strip()
        ]

        # --- Blue Jay PMS ------------------------------------------------
        # Never hard-code credentials. All values come from the environment.
        self.bluejay_base_url: str | None = os.getenv("BLUEJAY_BASE_URL") or None
        self.bluejay_api_key: str | None = os.getenv("BLUEJAY_API_KEY") or None
        self.bluejay_property_ids: list[str] = [
            p.strip() for p in os.getenv("BLUEJAY_PROPERTY_IDS", "").split(",") if p.strip()
        ]
        self.bluejay_timeout_seconds: float = float(os.getenv("BLUEJAY_TIMEOUT_SECONDS", "15"))

        # --- Market data -------------------------------------------------
        self.market_user_agent: str = os.getenv(
            "MARKET_USER_AGENT",
            "DynamicPricingProperty/0.1 (+localhost MVP; contact: ops@luminous.example)",
        )
        self.market_http_timeout_seconds: float = float(
            os.getenv("MARKET_HTTP_TIMEOUT_SECONDS", "10")
        )
        self.market_public_enabled: bool = (
            os.getenv("MARKET_PUBLIC_ENABLED", "false").strip().lower() == "true"
        )

        self.seed_on_startup: bool = (
            os.getenv("SEED_ON_STARTUP", "true").strip().lower() == "true"
        )
        self.demo_seed: int = int(os.getenv("DEMO_SEED", "20260822"))

    @property
    def bluejay_configured(self) -> bool:
        return bool(self.bluejay_base_url and self.bluejay_api_key)

    def redacted(self) -> dict:
        """Safe-to-display view. Never leaks secret values."""
        return {
            "data_provider": self.data_provider,
            "market_provider": self.market_provider,
            "database_url": self.database_url,
            "bluejay_base_url": self.bluejay_base_url,
            "bluejay_api_key_present": bool(self.bluejay_api_key),
            "bluejay_configured": self.bluejay_configured,
            "market_public_enabled": self.market_public_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
