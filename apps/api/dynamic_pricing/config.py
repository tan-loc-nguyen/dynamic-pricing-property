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

from dotenv import load_dotenv

from .packaging import REPO_ROOT, is_frozen, user_data_dir

load_dotenv(REPO_ROOT / ".env", override=False)


class Settings:
    """Environment-driven settings. Plain class: no magic, easy to read."""

    def __init__(self) -> None:
        self.data_provider: str = os.getenv("DATA_PROVIDER", "mock").strip().lower()
        self.market_provider: str = os.getenv("MARKET_PROVIDER", "mock").strip().lower()

        # A source checkout keeps using data/ at the repo root. A packaged
        # build must NOT: its bundle is a temp directory PyInstaller deletes on
        # exit, which would take every recorded decision with it.
        data_dir = user_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        default_db = data_dir / "dynamic_pricing.db"
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
        # How the key is presented. UNVERIFIED: the API document states only
        # that it goes in "the Header". BLUEJAY_HOTEL_ID replaced the old
        # BLUEJAY_PROPERTY_IDS, which nothing reads any more.
        self.bluejay_auth_header: str = os.getenv("BLUEJAY_AUTH_HEADER", "X-API-KEY").strip()
        self.bluejay_auth_style: str = os.getenv("BLUEJAY_AUTH_STYLE", "raw").strip().lower()
        self.bluejay_timeout_seconds: float = float(os.getenv("BLUEJAY_TIMEOUT_SECONDS", "15"))
        self.bluejay_hotel_id: str = os.getenv("BLUEJAY_HOTEL_ID", "").strip()
        # user_data_dir(), NOT REPO_ROOT — for exactly the reason the database
        # above uses it. In a --onefile build REPO_ROOT resolves inside
        # PyInstaller's extraction directory, which is deleted on exit, so a
        # snapshot placed there could never be found by the shipped app. And
        # SNAPSHOT is meant to be the standing client-demo source, i.e. the mode
        # that matters most in a packaged build.
        #
        # A source checkout keeps using apps/api/snapshots/, which is gitignored:
        # the test tenant is a third party's hotel and this repo is public.
        default_snapshots = (
            data_dir / "snapshots" / "current"
            if is_frozen()
            else REPO_ROOT / "apps" / "api" / "snapshots" / "current"
        )
        self.bluejay_snapshot_dir: str = os.getenv(
            "BLUEJAY_SNAPSHOT_DIR", str(default_snapshots)
        )

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
