"""PMSProvider interface + vendor-neutral DTOs.

Nothing outside ``providers/pms`` may know that Blue Jay exists. Adapters map
vendor payloads into these DTOs; the sync service persists DTOs into the domain
model; everything downstream sees only domain objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


class ProviderUnavailable(RuntimeError):
    """Raised when an external provider cannot serve a request.

    Callers are expected to catch this and fall back to demo/cached data — an
    integration outage must never take the product down.
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


@dataclass(frozen=True)
class PropertyDTO:
    external_id: str
    name: str
    city: str = "Ho Chi Minh City"
    district: str = ""
    currency: str = "VND"
    timezone_name: str = "Asia/Ho_Chi_Minh"


@dataclass(frozen=True)
class RoomDTO:
    external_id: str
    property_external_id: str
    name: str
    room_type: str = "Studio"
    capacity: int = 2
    units_total: int = 1
    base_price: float = 0.0
    min_price: float | None = None
    max_price: float | None = None
    is_active: bool = True


@dataclass(frozen=True)
class InventoryDTO:
    room_external_id: str
    stay_date: date
    units_total: int
    units_sold: int
    current_price: float
    is_event: bool = False
    event_name: str | None = None
    season: str | None = None
    historical_occupancy: float | None = None
    historical_avg_price: float | None = None


@dataclass(frozen=True)
class BookingDTO:
    external_id: str
    room_external_id: str
    stay_date: date
    booked_at: date
    nights: int = 1
    guests: int = 2
    price: float = 0.0
    channel: str = "Airbnb"
    status: str = "confirmed"


class PMSProvider(ABC):
    """Stable contract for any property-management system."""

    name: str = "abstract"
    mode: str = "unknown"
    supports_price_push: bool = False

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    def fetch_properties(self) -> list[PropertyDTO]: ...

    @abstractmethod
    def fetch_rooms(self) -> list[RoomDTO]: ...

    @abstractmethod
    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]: ...

    @abstractmethod
    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]: ...

    def push_price(self, room_external_id: str, stay_date: date, price: float) -> None:
        """Write a price back to the PMS.

        Out of scope for the MVP (autonomous OTA updates are an explicit
        non-goal). The hook exists so the seam is visible.
        """
        raise ProviderUnavailable(
            self.name,
            "Writing prices back to the PMS is not enabled in the MVP.",
            remediation="Operator applies approved prices manually for now.",
        )
