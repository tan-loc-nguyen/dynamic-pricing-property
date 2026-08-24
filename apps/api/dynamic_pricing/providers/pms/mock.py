"""MockPMSProvider — the Luminous portfolio, synthesised.

Demo mode is a first-class provider, not a fixture file: the same sync path
that will ingest Blue Jay ingests this, so the normalization boundary is
exercised on every run.

PORTFOLIO — from the client document (VALIDATED):
    22 apartments, 3 room categories: 2BR Regular, 2BR Premium, 3BR.

The split of 22 units across the three categories is NOT stated in the client
document. The 10/8/4 split below is a placeholder — see ASSUMPTIONS.md (U11).

Everything else here (occupancy shapes, booking timing, current NET rates) is
synthetic and deterministic: same seed -> same portfolio.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from ...features.booking_curve import DemoBookingCurveProvider
from ...pricing.rate_book import (
    CATEGORY_2BR_PREMIUM,
    CATEGORY_2BR_REGULAR,
    CATEGORY_3BR,
    SeasonalRateBook,
)
from .base import (
    BookingDTO,
    InventoryDTO,
    PhysicalRoomDTO,
    PMSProvider,
    PropertyDTO,
    ProviderStatus,
    RoomTypeDTO,
)

HORIZON_DAYS = 90   # far enough to cross a season boundary in the demo
HISTORY_DAYS = 45

PROPERTY = PropertyDTO(
    external_id="LUM-HCM",
    name="Luminous Luxury Apartments",
    city="Ho Chi Minh City",
    district="",
)

# (external_id, category, display name, capacity, units)
# 22 units total — the split is UNVALIDATED (U11).
ROOM_TYPE_SPECS = [
    ("LUM-2BR-REG", CATEGORY_2BR_REGULAR, "2BR Regular", 4, 10),
    ("LUM-2BR-PRM", CATEGORY_2BR_PREMIUM, "2BR Premium", 4, 8),
    ("LUM-3BR", CATEGORY_3BR, "3BR", 6, 4),
]
TOTAL_UNITS = sum(spec[4] for spec in ROOM_TYPE_SPECS)
assert TOTAL_UNITS == 22, "the client states 22 apartments"

# Demand personality per category — how quickly each fills. UNVALIDATED.
_DEMAND_BIAS = {
    CATEGORY_2BR_REGULAR: 1.00,
    CATEGORY_2BR_PREMIUM: 0.94,
    CATEGORY_3BR: 0.86,
}

# Stay dates (day-offsets from "today") forced into a specific shape so the
# demo always contains every teaching scenario the operator needs to see.
SCENARIO_PLAN: dict[int, dict] = {
    2:  {"tag": "close_in_far_behind_pace", "occupancy": 0.10, "pickup": 0},
    3:  {"tag": "close_in_ahead_of_pace", "occupancy": 0.95, "pickup": 3},
    6:  {"tag": "behind_pace_near", "occupancy": 0.30, "pickup": 0},
    9:  {"tag": "pickup_surging", "occupancy": 0.72, "pickup": 5},
    13: {"tag": "floor_candidate", "occupancy": 0.05, "pickup": 0},
    18: {"tag": "on_pace", "occupancy": 0.55, "pickup": 1},
    24: {"tag": "cap_candidate", "occupancy": 0.96, "pickup": 6},
    29: {"tag": "pickup_stalled", "occupancy": 0.34, "pickup": 0},
    35: {"tag": "strong_market", "occupancy": 0.55, "pickup": 2, "market": "strong"},
    41: {"tag": "weak_market", "occupancy": 0.30, "pickup": 0, "market": "weak"},
    47: {"tag": "low_confidence_market_only", "occupancy": 0.45, "pickup": 1, "market": "low_conf"},
    54: {"tag": "no_market_data", "occupancy": 0.40, "pickup": 1, "market": "none"},
    62: {"tag": "far_out_ahead", "occupancy": 0.42, "pickup": 2},
    75: {"tag": "far_out_quiet", "occupancy": 0.06, "pickup": 0},
    84: {"tag": "season_boundary", "occupancy": 0.30, "pickup": 1},
}


class MockPMSProvider(PMSProvider):
    name = "MockPMSProvider"
    mode = "mock"
    supports_rate_push = False

    def __init__(self, seed: int = 20260822, today: date | None = None) -> None:
        self.seed = seed
        self.today = today or date.today()
        self.rate_book = SeasonalRateBook()
        # Demo occupancy is generated AROUND the same booking curve the feature
        # engine measures against, so pace gaps spread realistically either side
        # of zero instead of every date reading 'behind pace'.
        self.curve = DemoBookingCurveProvider()

    # ------------------------------------------------------------------
    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            healthy=True,
            mode=self.mode,
            detail=(
                f"Synthetic Luminous portfolio: {TOTAL_UNITS} apartments across "
                f"{len(ROOM_TYPE_SPECS)} room categories, {HORIZON_DAYS}-day forward horizon."
            ),
        )

    def fetch_properties(self) -> list[PropertyDTO]:
        return [PROPERTY]

    def fetch_room_types(self) -> list[RoomTypeDTO]:
        out = []
        for ext_id, category, name, capacity, units in ROOM_TYPE_SPECS:
            band = self.rate_book.lookup(category, self.today)
            out.append(
                RoomTypeDTO(
                    external_id=ext_id,
                    property_external_id=PROPERTY.external_id,
                    name=name,
                    category=category,
                    capacity=capacity,
                    units_total=units,
                    fallback_base_net_rate=band.base_net_rate if band else 2_000_000,
                    fallback_min_net_rate=band.min_net_rate if band else 1_500_000,
                    fallback_max_net_rate=band.max_net_rate if band else 4_000_000,
                )
            )
        return out

    def fetch_physical_rooms(self) -> list[PhysicalRoomDTO]:
        """The 22 individual apartments. Inventory only — they do not carry rates."""
        rooms: list[PhysicalRoomDTO] = []
        for ext_id, _category, _name, _capacity, units in ROOM_TYPE_SPECS:
            prefix = ext_id.replace("LUM-", "")
            for i in range(1, units + 1):
                floor = str(((i - 1) % 5) + 3)  # floors 3..7
                rooms.append(
                    PhysicalRoomDTO(
                        external_id=f"{ext_id}-U{i:02d}",
                        room_type_external_id=ext_id,
                        unit_label=f"{prefix}-{floor}{i:02d}",
                        floor=floor,
                    )
                )
        return rooms

    # ------------------------------------------------------------------
    def fetch_inventory(self, start: date, end: date) -> list[InventoryDTO]:
        rows: list[InventoryDTO] = []
        for ext_id, category, _name, _capacity, units in ROOM_TYPE_SPECS:
            rng = random.Random(f"{self.seed}:{ext_id}:inventory")
            current = start
            while current <= end:
                rows.append(self._inventory_row(ext_id, category, units, current, rng))
                current += timedelta(days=1)
        return rows

    def _inventory_row(
        self, ext_id: str, category: str, units: int, stay_date: date, rng: random.Random
    ) -> InventoryDTO:
        offset = (stay_date - self.today).days
        plan = SCENARIO_PLAN.get(offset, {})
        weekday = stay_date.weekday()
        band = self.rate_book.lookup(category, stay_date)

        # Expected on-the-books occupancy for this lead time, then dispersed
        # around it so some dates run ahead of pace and some behind.
        expected = self.curve.expected_occupancy(
            category, band.season_key if band else None, max(offset, 0)
        ) or 0.4
        weekday_lift = {0: 0.94, 1: 0.94, 2: 0.97, 3: 1.02, 4: 1.12, 5: 1.14, 6: 1.04}[weekday]
        occupancy = expected * weekday_lift * _DEMAND_BIAS[category]
        occupancy *= rng.uniform(0.72, 1.30)

        if offset < 0:  # historical rows settle at a realised occupancy
            occupancy = min(0.98, max(0.30, occupancy + 0.40))
        if "occupancy" in plan:
            occupancy = plan["occupancy"]

        occupancy = min(1.0, max(0.0, occupancy))
        units_sold = min(units, max(0, int(round(occupancy * units))))

        # Current NET rate = what the operator has set today. Static within a
        # season (the client's table gives only 3 levels per 2-3 month season),
        # which is exactly the gap this product exists to close.
        current_net = band.base_net_rate if band else 2_000_000
        if plan.get("tag") == "floor_candidate":
            current_net = band.min_net_rate if band else current_net
        elif plan.get("tag") == "cap_candidate":
            current_net = band.max_net_rate if band else current_net

        return InventoryDTO(
            room_type_external_id=ext_id,
            stay_date=stay_date,
            units_total=units,
            units_sold=units_sold,
            current_net_rate=float(current_net),
            current_ota_price=None,  # not known without a channel manager feed
            historical_occupancy=round(min(0.97, max(0.20, occupancy + rng.uniform(-0.10, 0.10))), 4),
            historical_avg_net_rate=round((band.base_net_rate if band else 2_000_000) * rng.uniform(0.95, 1.06), -4),
        )

    # ------------------------------------------------------------------
    def fetch_bookings(self, start: date, end: date) -> list[BookingDTO]:
        """Bookings with realistic *booked_at* dates.

        Recent pickup is measured over a window, so the generator has to place
        bookings on a plausible timeline rather than just emit a count.
        """
        bookings: list[BookingDTO] = []
        counter = 0
        for ext_id, category, _name, capacity, units in ROOM_TYPE_SPECS:
            rng = random.Random(f"{self.seed}:{ext_id}:bookings")
            # Must be the SAME sequential stream fetch_inventory uses, or the
            # bookings emitted here describe a different occupancy than the one
            # persisted -- pickup could exceed units sold.
            inv_rng = random.Random(f"{self.seed}:{ext_id}:inventory")
            current = start
            while current <= end:
                offset = (current - self.today).days
                plan = SCENARIO_PLAN.get(offset, {})
                inv = self._inventory_row(ext_id, category, units, current, inv_rng)
                total_sold = inv.units_sold
                recent = (
                    min(total_sold, int(plan["pickup"]))
                    if "pickup" in plan
                    else min(total_sold, rng.choice([0, 1, 1, 2]))
                )

                for i in range(total_sold):
                    if i < recent:
                        booked_at = self.today - timedelta(days=rng.randint(0, 6))
                    else:
                        lead = rng.randint(10, 90)
                        booked_at = current - timedelta(days=lead)
                        if booked_at > self.today - timedelta(days=7):
                            booked_at = self.today - timedelta(days=rng.randint(8, 50))
                    booked_at = min(booked_at, current)
                    counter += 1
                    bookings.append(
                        BookingDTO(
                            external_id=f"BK-{ext_id}-{counter:05d}",
                            room_type_external_id=ext_id,
                            stay_date=current,
                            booked_at=booked_at,
                            nights=rng.choice([1, 2, 2, 3, 4, 5]),
                            guests=rng.randint(2, capacity),
                            net_rate=inv.current_net_rate,
                            channel=rng.choice(
                                ["Airbnb", "Booking.com", "Agoda", "Trip.com", "Expedia", "Direct"]
                            ),
                        )
                    )
                current += timedelta(days=1)
        return bookings
