"""PMSProvider interface + vendor-neutral DTOs.

Nothing outside ``providers/pms`` may know that Blue Jay exists. Adapters map
vendor payloads into these DTOs; the sync service persists DTOs into the
domain model; everything downstream sees only domain objects.

All rates in these DTOs are **NET** unless the field name says otherwise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


class ProviderUnavailable(RuntimeError):
    """Raised when an external provider cannot serve a request.

    Callers catch this and fall back to demo/cached data — an integration
    outage must never take the product down.
    """

    def __init__(self, provider: str, message: str, *, remediation: str = "") -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.remediation = remediation


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    healthy: bool
    mode: str
    detail: str = ""
    remediation: str = ""
    unresolved_mappings: list[str] = field(default_factory=list)
    #: Warnings about the DATA ITSELF — that a snapshot may still hold guest
    #: information, or that its pseudonyms are recoverable. Deliberately NOT
    #: `unresolved_mappings`: that field is named for room-type mapping gaps,
    #: and a guest-data warning shown under a heading about mappings reads as a
    #: configuration nit instead of as the warning it is.
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PropertyDTO:
    external_id: str
    name: str
    city: str = "Ho Chi Minh City"
    district: str = ""
    currency: str = "VND"
    timezone_name: str = "Asia/Ho_Chi_Minh"


@dataclass(frozen=True)
class RoomTypeDTO:
    external_id: str
    property_external_id: str
    name: str
    category: str
    capacity: int = 4
    units_total: int = 1
    # Fallback only — live MIN/BASE/MAX come from the validated SeasonalRateBook.
    fallback_base_net_rate: float = 0.0
    fallback_min_net_rate: float = 0.0
    fallback_max_net_rate: float = 0.0
    is_active: bool = True


@dataclass(frozen=True)
class PhysicalRoomDTO:
    external_id: str
    room_type_external_id: str
    unit_label: str
    floor: str | None = None
    is_active: bool = True


#: Every value ``rate_provenance`` can take, in one place.
#:
#: ONE definition, because the frontend must render each of them and was
#: previously matching against a guess: `seasonal_base` was emitted, never
#: translated, and drew a styled empty box. Guarded in both directions by
#: tests/test_localisation.py.
RATE_PROVENANCE_VALUES: tuple[str, ...] = (
    "published",       # the PMS states a forward rate. Blue Jay does not.
    "derived_adr",     # reconstructed from bookings on THIS night
    "last_known_adr",  # reconstructed from recent bookings for the category
    "seasonal_base",   # the validated band's BASE for that date's season
    "unavailable",     # no source produced a rate at all
)


@dataclass(frozen=True)
class InventoryDTO:
    room_type_external_id: str
    stay_date: date
    units_total: int
    units_sold: int
    current_net_rate: float
    current_ota_price: float | None = None
    historical_occupancy: float | None = None
    historical_avg_net_rate: float | None = None
    #: WHERE current_net_rate came from: "published" when the PMS states a
    #: forward rate, "derived_adr" / "last_known_adr" when it was reconstructed
    #: from bookings, "seasonal_base" when nothing was available. Blue Jay
    #: exposes no forward rate at all, so a realized average often stands in
    #: for a list price -- and an operator must never read one as the other.
    rate_provenance: str = "published"


@dataclass(frozen=True)
class BookingDTO:
    external_id: str
    room_type_external_id: str
    stay_date: date
    booked_at: date
    nights: int = 1
    guests: int = 2
    net_rate: float = 0.0
    channel: str = "Airbnb"
    status: str = "confirmed"
    physical_room_external_id: str | None = None


class PMSProvider(ABC):
    """Stable contract for any property-management system."""

    name: str = "abstract"
    mode: str = "unknown"
    supports_rate_push: bool = False

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    def fetch_properties(self) -> list[PropertyDTO]: ...

    @abstractmethod
    def fetch_room_types(self) -> list[RoomTypeDTO]: ...

    @abstractmethod
    def fetch_physical_rooms(self) -> list[PhysicalRoomDTO]: ...

    @abstractmethod
    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]: ...

    @abstractmethod
    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]: ...

    def push_rate(self, room_type_external_id: str, stay_date: date, net_rate: float) -> None:
        """Write a rate back to the PMS.

        NOT enabled: the product runs in Shadow Mode. Blue Jay remains the
        execution layer; this hook exists so the seam is visible.
        """
        raise ProviderUnavailable(
            self.name,
            "Rate push is disabled — the product runs in Shadow Mode.",
            remediation="The operator applies approved NET rates in Blue Jay manually.",
        )
