"""ManualMarketDataProvider — operator-entered reference rates.

The operator is the collector. Observations arrive through the Market Data
screen and are persisted directly, so ``collect()`` is intentionally a no-op.

This is the only path that can produce HIGH confidence, because it is the only
one where a human can state the price basis: is this a NET rate, does it
include taxes and fees, which length of stay, was it promotional?
"""

from __future__ import annotations

from datetime import date

from ..pms.base import ProviderStatus
from .base import CONFIDENCE_HIGH, MarketDataProvider, MarketObservationDTO


class ManualMarketDataProvider(MarketDataProvider):
    name = "ManualMarketDataProvider"
    mode = "manual"
    max_confidence = CONFIDENCE_HIGH

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=(
                "Operator-entered comp-set rates. The only source that can reach HIGH "
                "confidence, because the operator can state the price basis."
            ),
        )

    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        return []  # nothing to poll — the API writes these directly
