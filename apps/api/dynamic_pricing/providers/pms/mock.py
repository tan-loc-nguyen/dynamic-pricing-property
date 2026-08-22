"""MockPMSProvider — a realistic synthetic Luminous-like portfolio.

Demo mode is a first-class provider, not a fixture file. The same sync path
that would ingest Blue Jay ingests this, so the normalization boundary is
exercised on every single run.

Fully deterministic: seeded RNG, caller-supplied "today". Same seed -> same
portfolio, so screenshots and tests stay stable.

The generator deliberately plants recognisable teaching scenarios (see
SCENARIO_PLAN below) so an operator can see *why* prices move.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from .base import BookingDTO, InventoryDTO, PMSProvider, PropertyDTO, ProviderStatus, RoomDTO

HORIZON_DAYS = 60
HISTORY_DAYS = 45  # past stay dates, used for historical occupancy/price features


@dataclass(frozen=True)
class _RoomSpec:
    external_id: str
    property_external_id: str
    name: str
    room_type: str
    capacity: int
    units_total: int
    base_price: float
    min_price: float
    max_price: float
    demand_bias: float  # >1 = naturally busier room


PROPERTY_SPECS = [
    PropertyDTO("LUM-D1", "Luminous Saigon Riverside", "Ho Chi Minh City", "District 1"),
    PropertyDTO("LUM-D2", "Luminous Thao Dien Residences", "Ho Chi Minh City", "Thu Duc"),
    PropertyDTO("LUM-DN", "Luminous Da Nang Beachfront", "Da Nang", "Son Tra"),
]

ROOM_SPECS = [
    _RoomSpec("LUM-D1-STU", "LUM-D1", "Riverside Studio", "Studio", 2, 6, 1_350_000, 850_000, 3_000_000, 1.00),
    _RoomSpec("LUM-D1-1BR", "LUM-D1", "Riverside One-Bedroom", "1-Bedroom", 3, 5, 1_850_000, 1_100_000, 4_200_000, 1.05),
    # max_price is a deliberately BINDING cap (channel-parity / owner instruction):
    # it triggers before the global compounding guardrail, so the demo shows a real cap.
    _RoomSpec("LUM-D1-2BR", "LUM-D1", "Riverside Two-Bedroom Suite", "2-Bedroom", 5, 3, 2_900_000, 1_800_000, 3_150_000, 0.92),
    _RoomSpec("LUM-D2-STU", "LUM-D2", "Thao Dien Garden Studio", "Studio", 2, 8, 1_150_000, 700_000, 2_600_000, 0.95),
    _RoomSpec("LUM-D2-1BR", "LUM-D2", "Thao Dien One-Bedroom", "1-Bedroom", 3, 6, 1_600_000, 1_000_000, 3_600_000, 1.00),
    # min_price is a deliberately BINDING floor (owner will not go below this).
    _RoomSpec("LUM-D2-LFT", "LUM-D2", "Thao Dien Duplex Loft", "Loft", 4, 2, 2_400_000, 2_150_000, 5_200_000, 0.88),
    _RoomSpec("LUM-DN-SEA", "LUM-DN", "Beachfront Sea-View Studio", "Studio", 2, 7, 1_500_000, 900_000, 3_400_000, 1.10),
    _RoomSpec("LUM-DN-1BR", "LUM-DN", "Beachfront One-Bedroom", "1-Bedroom", 3, 4, 2_100_000, 1_300_000, 4_800_000, 1.02),
]

# Stay dates (as day-offsets from "today") that are forced into a specific
# shape so the demo always contains every teaching scenario.
SCENARIO_PLAN: dict[int, dict] = {
    2:  {"tag": "close_in_low_occ", "occupancy": 0.15, "pickup": 0},
    3:  {"tag": "close_in_high_occ", "occupancy": 0.90, "pickup": 3},
    5:  {"tag": "weak_pace_near", "occupancy": 0.30, "pickup": 0},
    9:  {"tag": "strong_pace", "occupancy": 0.70, "pickup": 4},
    12: {"tag": "underpriced_by_operator", "occupancy": 0.05, "pickup": 0, "force_low_price": True},
    16: {"tag": "event", "occupancy": 0.85, "pickup": 3, "event": "Saigon River Music Festival"},
    17: {"tag": "event_shoulder", "occupancy": 0.75, "pickup": 2},
    23: {"tag": "overpriced_by_operator", "occupancy": 0.95, "pickup": 5, "force_high_price": True},
    27: {"tag": "normal_weekday", "occupancy": 0.55, "pickup": 1},
    31: {"tag": "strong_market", "occupancy": 0.60, "pickup": 2, "market": "strong"},
    35: {"tag": "weak_market", "occupancy": 0.35, "pickup": 0, "market": "weak"},
    38: {"tag": "event", "occupancy": 0.80, "pickup": 3, "event": "National Day long weekend"},
    44: {"tag": "no_market_data", "occupancy": 0.50, "pickup": 1, "market": "none"},
    52: {"tag": "far_out_quiet", "occupancy": 0.20, "pickup": 0},
}


class MockPMSProvider(PMSProvider):
    name = "MockPMSProvider"
    mode = "mock"
    supports_price_push = False

    def __init__(self, seed: int = 20260822, today: date | None = None) -> None:
        self.seed = seed
        self.today = today or date.today()

    # ------------------------------------------------------------------
    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=(
                f"Synthetic Luminous-like portfolio: {len(PROPERTY_SPECS)} properties, "
                f"{len(ROOM_SPECS)} room types, {HORIZON_DAYS}-day forward horizon."
            ),
        )

    def fetch_properties(self) -> list[PropertyDTO]:
        return list(PROPERTY_SPECS)

    def fetch_rooms(self) -> list[RoomDTO]:
        return [
            RoomDTO(
                external_id=s.external_id,
                property_external_id=s.property_external_id,
                name=s.name,
                room_type=s.room_type,
                capacity=s.capacity,
                units_total=s.units_total,
                base_price=s.base_price,
                min_price=s.min_price,
                max_price=s.max_price,
            )
            for s in ROOM_SPECS
        ]

    # ------------------------------------------------------------------
    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]:
        rows: list[InventoryDTO] = []
        for spec in ROOM_SPECS:
            rng = random.Random(f"{self.seed}:{spec.external_id}:inventory")
            current = start
            while current <= end:
                rows.append(self._inventory_row(spec, current, rng))
                current += timedelta(days=1)
        return rows

    def _inventory_row(self, spec: _RoomSpec, stay_date: date, rng: random.Random) -> InventoryDTO:
        offset = (stay_date - self.today).days
        plan = SCENARIO_PLAN.get(offset, {})
        weekday = stay_date.weekday()

        # Baseline occupancy shape: weekends busier, far-out dates emptier.
        weekday_lift = {0: 0.00, 1: 0.00, 2: 0.03, 3: 0.08, 4: 0.20, 5: 0.24, 6: 0.10}[weekday]
        horizon_decay = max(0.0, 1.0 - (max(offset, 0) / (HORIZON_DAYS * 1.6)))
        occupancy = (0.30 + weekday_lift) * (0.55 + 0.75 * horizon_decay) * spec.demand_bias
        occupancy += rng.uniform(-0.10, 0.12)

        if offset < 0:  # historical rows settle at a plausible realised occupancy
            occupancy = min(0.98, max(0.25, occupancy + 0.35))

        if "occupancy" in plan:
            occupancy = plan["occupancy"]

        occupancy = min(1.0, max(0.0, occupancy))
        units_sold = int(round(occupancy * spec.units_total))
        units_sold = min(spec.units_total, max(0, units_sold))

        # "Current price" = what the operator has manually set today. Slightly
        # noisy and weekday-naive on purpose: the recommendation should have
        # something meaningful to correct.
        price = spec.base_price * (1.0 + (0.06 if weekday >= 4 else 0.0))
        price *= 1.0 + rng.uniform(-0.05, 0.05)
        # A plausible manual mispricing the copilot should catch -- not an extreme.
        if plan.get("force_low_price"):
            price = spec.base_price * 0.72
        if plan.get("force_high_price"):
            price = spec.base_price * 1.45
        price = round(price / 10_000) * 10_000

        event_name = plan.get("event")
        return InventoryDTO(
            room_external_id=spec.external_id,
            stay_date=stay_date,
            units_total=spec.units_total,
            units_sold=units_sold,
            current_price=float(price),
            is_event=bool(event_name),
            event_name=event_name,
            season=None,
            historical_occupancy=round(min(0.97, max(0.20, occupancy + rng.uniform(-0.12, 0.12))), 4),
            historical_avg_price=round(spec.base_price * rng.uniform(0.92, 1.10), -4),
        )

    # ------------------------------------------------------------------
    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]:
        """Generate bookings whose *booked_at* dates reproduce the intended pace.

        Booking pace is measured over a recent lookback window, so the
        generator has to place bookings on a realistic timeline rather than
        just emit a count.
        """
        bookings: list[BookingDTO] = []
        counter = 0
        for spec in ROOM_SPECS:
            rng = random.Random(f"{self.seed}:{spec.external_id}:bookings")
            current = start
            while current <= end:
                offset = (current - self.today).days
                plan = SCENARIO_PLAN.get(offset, {})
                inv = self._inventory_row(spec, current, random.Random(f"{self.seed}:{spec.external_id}:inventory-{current}"))
                total_sold = inv.units_sold

                # How many of those sales landed inside the recent pace window?
                if "pickup" in plan:
                    recent = min(total_sold, int(plan["pickup"]))
                else:
                    recent = min(total_sold, rng.choice([0, 1, 1, 2]))

                for i in range(total_sold):
                    if i < recent:
                        booked_at = self.today - timedelta(days=rng.randint(0, 6))
                    else:
                        lead = rng.randint(10, 75)
                        booked_at = current - timedelta(days=lead)
                        if booked_at > self.today - timedelta(days=7):
                            booked_at = self.today - timedelta(days=rng.randint(8, 40))
                    if booked_at > current:
                        booked_at = current
                    counter += 1
                    bookings.append(
                        BookingDTO(
                            external_id=f"BK-{spec.external_id}-{counter:05d}",
                            room_external_id=spec.external_id,
                            stay_date=current,
                            booked_at=booked_at,
                            nights=rng.choice([1, 1, 2, 2, 3, 4]),
                            guests=rng.randint(1, spec.capacity),
                            price=inv.current_price,
                            channel=rng.choice(
                                ["Airbnb", "Booking.com", "Agoda", "Trip.com", "Expedia", "Direct"]
                            ),
                        )
                    )
                current += timedelta(days=1)
        return bookings
