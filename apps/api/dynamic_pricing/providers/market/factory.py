"""Market provider selection."""

from __future__ import annotations

from datetime import date

from ...config import get_settings
from .base import MarketDataProvider
from .manual import ManualMarketDataProvider
from .mock import MockMarketDataProvider
from .public_web import PublicWebMarketDataProvider

_REGISTRY: dict[str, type[MarketDataProvider]] = {
    "mock": MockMarketDataProvider,
    "manual": ManualMarketDataProvider,
    "public_web": PublicWebMarketDataProvider,
}


def get_market_provider(name: str | None = None, today: date | None = None) -> MarketDataProvider:
    settings = get_settings()
    key = (name or settings.market_provider or "mock").lower()
    cls = _REGISTRY.get(key, MockMarketDataProvider)
    if cls is MockMarketDataProvider:
        return MockMarketDataProvider(seed=settings.demo_seed, today=today)
    return cls()


def list_market_providers() -> list[str]:
    return sorted(_REGISTRY)
