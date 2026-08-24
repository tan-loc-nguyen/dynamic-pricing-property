"""Market provider selection."""

from __future__ import annotations

from datetime import date

from ...config import get_settings
from ...lookup import resolve
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
    """Resolve a market provider. An unknown key RAISES rather than substituting.

    Silent substitution here persisted synthetic mock observations and reported
    them as a successful public-web collection, on a hyphen-for-underscore typo
    in a user-supplied query parameter.
    """
    settings = get_settings()
    cls = resolve(
        _REGISTRY,
        name or settings.market_provider,
        kind="market provider",
        default="mock",
    )
    if cls is MockMarketDataProvider:
        return MockMarketDataProvider(seed=settings.demo_seed, today=today)
    return cls()


def list_market_providers() -> list[str]:
    return sorted(_REGISTRY)
