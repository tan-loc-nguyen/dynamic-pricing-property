"""ManualMarketDataProvider — operator-entered reference prices.

The operator is the collector here. Observations arrive through the Market
Data screen (POST /api/market/observations) and are persisted directly, so
``collect()`` is intentionally a no-op: there is nothing to poll.

This is the fallback that keeps the market signal alive when automated
collection is unavailable or legally off-limits.
"""

from __future__ import annotations

from datetime import date

from ..pms.base import ProviderStatus
from .base import MarketDataProvider, MarketObservationDTO


class ManualMarketDataProvider(MarketDataProvider):
    name = "ManualMarketDataProvider"
    mode = "manual"

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=(
                "Market observations are entered by the operator on the Market Data screen "
                "and stored with source, price, timestamp and notes."
            ),
        )

    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        # Nothing to poll: manual observations are written directly by the API.
        return []
