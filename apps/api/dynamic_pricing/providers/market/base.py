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


# Why an observation scored the way it did. Operator-facing on the Market
# screen -- it is the whole basis for trusting or discarding a competitor price
# -- so it is emitted as codes and rendered in the viewer's language, the same
# way the pricing explanation is. Checked against both locale files by test.
CONFIDENCE_REASON_CODES: tuple[str, ...] = (
    "no_price",
    "comparable_net",
    "known_basis",
    "not_comparable",
)
CONFIDENCE_GAP_CODES: tuple[str, ...] = (
    "no_room_category",
    "basis_unknown",
    "tax_unknown",
    "fee_unknown",
    "los_unknown",
    "promotion_unknown",
)


def score_confidence(dto: MarketObservationDTO) -> tuple[str, str, list[str]]:
    """Derive a confidence level from what we actually know about the price.

    Returns (confidence, reason_code, gap_codes). Deliberately conservative:
    an unknown basis can never be HIGH, because a number you cannot interpret
    should not move a rate.
    """
    if dto.observed_price is None or dto.observed_price <= 0:
        return CONFIDENCE_UNUSABLE, "no_price", []

    gaps: list[str] = []
    if not dto.room_category:
        gaps.append("no_room_category")
    if dto.price_basis == BASIS_UNKNOWN:
        gaps.append("basis_unknown")
    if dto.tax_inclusion == "UNKNOWN":
        gaps.append("tax_unknown")
    if dto.fee_inclusion == "UNKNOWN":
        gaps.append("fee_unknown")
    if dto.length_of_stay is None:
        gaps.append("los_unknown")
    if dto.promotion_status == "UNKNOWN":
        gaps.append("promotion_unknown")

    if not gaps and dto.price_basis == BASIS_NET:
        return CONFIDENCE_HIGH, "comparable_net", []
    if len(gaps) <= 2 and dto.price_basis != BASIS_UNKNOWN and dto.room_category:
        return CONFIDENCE_MEDIUM, "known_basis", gaps
    return CONFIDENCE_LOW, "not_comparable", gaps


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
