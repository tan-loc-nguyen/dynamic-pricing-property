"""MarketDataProvider interface, observation DTO, and confidence scoring.

A competitor price is only useful if you know what it *is*. The same headline
number can be a refundable OTA sell price with taxes included for a 3-night
stay, or a net rate for one night — and only one of those is comparable to a
Luminous NET rate.

So provenance is first-class, and confidence is DERIVED from it rather than
asserted. Low-confidence evidence is kept and shown, but the pricing engine
will not act on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from ..pms.base import ProviderStatus, ProviderUnavailable

__all__ = [
    "MarketDataProvider",
    "MarketObservationDTO",
    "ProviderStatus",
    "ProviderUnavailable",
    "score_confidence",
]

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNUSABLE = "UNUSABLE"

BASIS_NET = "NET"
BASIS_OTA_SELL = "OTA_SELL"
BASIS_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MarketObservationDTO:
    """One observed reference price, with everything needed to judge it."""

    stay_date: date
    competitor_name: str
    observed_price: float
    source: str

    property_external_id: str | None = None
    room_type_external_id: str | None = None
    competitor_name_key: str | None = None

    # --- comparability metadata ---------------------------------------
    room_category: str | None = None
    length_of_stay: int | None = None
    guests: int | None = None
    price_basis: str = BASIS_UNKNOWN
    tax_inclusion: str = "UNKNOWN"       # INCLUSIVE | EXCLUSIVE | UNKNOWN
    fee_inclusion: str = "UNKNOWN"
    promotion_status: str = "UNKNOWN"    # NONE | PROMOTIONAL | UNKNOWN
    is_refundable: bool | None = None

    currency: str = "VND"
    source_url: str | None = None
    notes: str | None = None
    confidence: str | None = None        # None -> derived by score_confidence
    confidence_reason: str | None = None
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


def score_confidence(dto: MarketObservationDTO) -> tuple[str, str]:
    """Derive a confidence level from what we actually know about the price.

    Returns (confidence, human-readable reason). Deliberately conservative:
    an unknown basis can never be HIGH, because a number you cannot interpret
    should not move a rate.
    """
    if dto.observed_price is None or dto.observed_price <= 0:
        return CONFIDENCE_UNUSABLE, "No usable price value."

    gaps: list[str] = []
    if not dto.room_category:
        gaps.append("no comparable room category")
    if dto.price_basis == BASIS_UNKNOWN:
        gaps.append("price basis unknown (NET vs OTA sell)")
    if dto.tax_inclusion == "UNKNOWN":
        gaps.append("tax treatment unknown")
    if dto.fee_inclusion == "UNKNOWN":
        gaps.append("fee treatment unknown")
    if dto.length_of_stay is None:
        gaps.append("length of stay unknown")
    if dto.promotion_status == "UNKNOWN":
        gaps.append("promotion status unknown")

    if not gaps and dto.price_basis == BASIS_NET:
        return CONFIDENCE_HIGH, "Comparable NET rate with full basis metadata."
    if len(gaps) <= 2 and dto.price_basis != BASIS_UNKNOWN and dto.room_category:
        return (
            CONFIDENCE_MEDIUM,
            "Known price basis and comparable category; minor gaps: " + ", ".join(gaps) + ".",
        )
    return (
        CONFIDENCE_LOW,
        "Not reliably comparable to a Luminous NET rate — " + ", ".join(gaps) + ".",
    )


class MarketDataProvider(ABC):
    name: str = "abstract"
    mode: str = "unknown"
    # The best confidence this provider can ever produce.
    max_confidence: str = CONFIDENCE_LOW

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    def collect(self, start: date, end: date, **kwargs) -> list[MarketObservationDTO]:
        """Return observations for the window.

        MUST NOT raise on 'no data' — return an empty list. Raise
        ProviderUnavailable only for genuine outages or misconfiguration.
        """
        raise NotImplementedError
