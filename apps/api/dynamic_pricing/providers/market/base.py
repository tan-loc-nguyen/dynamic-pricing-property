"""MarketDataProvider interface + vendor-neutral observation DTO."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from ..pms.base import ProviderStatus, ProviderUnavailable

__all__ = ["MarketDataProvider", "MarketObservationDTO", "ProviderStatus", "ProviderUnavailable"]


@dataclass(frozen=True)
class MarketObservationDTO:
    """One observed reference price.

    Provenance is mandatory, not optional: an operator must always be able to
    ask "where did this number come from, and when?".
    """

    stay_date: date
    competitor_name: str
    observed_price: float
    source: str
    property_external_id: str | None = None
    room_external_id: str | None = None
    currency: str = "VND"
    source_url: str | None = None
    notes: str | None = None
    collected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


class MarketDataProvider(ABC):
    name: str = "abstract"
    mode: str = "unknown"

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        """Return observations for the window.

        Implementations MUST NOT raise on 'no data' — return an empty list.
        Raise ProviderUnavailable only for genuine outages/misconfiguration.
        """
        raise NotImplementedError
