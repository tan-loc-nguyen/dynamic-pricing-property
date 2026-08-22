"""FeatureEngine — turns normalized operational data into pricing signals.

    raw data -> normalized rows -> FeatureEngine -> PricingContext -> PricingEngine

This layer owns *measurement* only. It contains no pricing policy: it never
decides what a 78% occupancy is worth, only that occupancy is 78%. The two
config values it does read (`booking_pace.lookback_days`,
`booking_pace.expected_pickup_per_week`) define how a signal is *measured*,
not how it is priced.

Any future pricing engine can reuse this layer unchanged.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Booking, MarketObservation, Property, Room, StayDateInventory
from .context import PricingContext

WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class FeatureEngine:
    """Builds PricingContexts in bulk, with all lookups pre-loaded.

    Bulk loading keeps a full 1,400-row pricing run to a handful of queries
    instead of thousands of round trips.
    """

    def __init__(self, session: Session, config: dict, today: date | None = None) -> None:
        self.session = session
        self.config = config or {}
        self.today = today or date.today()

        pace_cfg = self.config.get("booking_pace", {})
        self.pace_lookback_days = int(pace_cfg.get("lookback_days", 7) or 7)
        self.expected_pickup_per_week = float(pace_cfg.get("expected_pickup_per_week", 1.0) or 1.0)

        self.season_labels = self.config.get("season", {}).get("month_labels", {})
        market_cfg = self.config.get("market", {})
        self.market_max_age_days = int(market_cfg.get("observation_max_age_days", 14) or 14)

        self._loaded = False
        self._rooms: dict[int, Room] = {}
        self._properties: dict[int, Property] = {}
        self._pickup: dict[tuple[int, date], float] = defaultdict(float)
        self._avg_lead_time: dict[int, float] = {}
        self._market_by_key: dict[tuple[int, date], list[MarketObservation]] = defaultdict(list)
        self._market_baseline: dict[int, float] = {}
        self._historical: dict[tuple[int, int], tuple[float, float]] = {}

    # ------------------------------------------------------------------ load
    def prepare(self) -> "FeatureEngine":
        """Pre-load every lookup the batch will need."""
        session = self.session

        self._rooms = {r.id: r for r in session.scalars(select(Room)).all()}
        self._properties = {p.id: p for p in session.scalars(select(Property)).all()}

        # --- booking pickup within the lookback window, per (room, stay_date)
        pace_cutoff = self.today - timedelta(days=self.pace_lookback_days)
        bookings = session.scalars(select(Booking).where(Booking.status != "cancelled")).all()

        lead_times: dict[int, list[int]] = defaultdict(list)
        for b in bookings:
            lead_times[b.room_id].append(b.lead_time_days)
            if pace_cutoff <= b.booked_at <= self.today:
                self._pickup[(b.room_id, b.stay_date)] += 1

        self._avg_lead_time = {
            room_id: round(statistics.fmean(values), 2)
            for room_id, values in lead_times.items()
            if values
        }

        # --- market observations, filtered by freshness
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_cutoff = now - timedelta(days=self.market_max_age_days)
        observations = session.scalars(select(MarketObservation)).all()

        per_room_prices: dict[int, list[float]] = defaultdict(list)
        room_ids_by_property: dict[int, list[int]] = defaultdict(list)
        for room in self._rooms.values():
            room_ids_by_property[room.property_id].append(room.id)

        for obs in observations:
            if obs.collected_at and obs.collected_at < age_cutoff:
                continue
            # A property-level observation applies to every room in that property.
            target_rooms = (
                [obs.room_id]
                if obs.room_id
                else room_ids_by_property.get(obs.property_id or -1, [])
            )
            for room_id in target_rooms:
                if room_id is None:
                    continue
                self._market_by_key[(room_id, obs.stay_date)].append(obs)
                per_room_prices[room_id].append(obs.observed_price)

        # Baseline = median observed market price for that room across the whole
        # horizon. Using the market's own central tendency (rather than our base
        # price) keeps the index independent of our pricing. See DECISIONS.md D5.
        self._market_baseline = {
            room_id: statistics.median(prices)
            for room_id, prices in per_room_prices.items()
            if prices
        }

        # --- historical reference: same room, same weekday, past stay dates
        past_rows = session.scalars(
            select(StayDateInventory).where(StayDateInventory.stay_date < self.today)
        ).all()
        grouped: dict[tuple[int, int], list[StayDateInventory]] = defaultdict(list)
        for row in past_rows:
            grouped[(row.room_id, row.stay_date.weekday())].append(row)
        for key, rows in grouped.items():
            occs = [r.occupancy for r in rows if r.occupancy is not None]
            prices = [r.current_price for r in rows if r.current_price]
            if occs and prices:
                self._historical[key] = (
                    round(statistics.fmean(occs), 4),
                    round(statistics.fmean(prices), 2),
                )

        self._loaded = True
        return self

    # ----------------------------------------------------------------- build
    def build(self, inventory: StayDateInventory) -> PricingContext:
        if not self._loaded:
            self.prepare()

        room = self._rooms.get(inventory.room_id)
        if room is None:
            room = self.session.get(Room, inventory.room_id)
        prop = self._properties.get(room.property_id) if room else None
        if prop is None and room is not None:
            prop = self.session.get(Property, room.property_id)

        missing: list[str] = []
        notes: list[str] = []

        # --- occupancy ---------------------------------------------------
        occupancy = inventory.occupancy
        if occupancy is None:
            missing.append("occupancy")

        # --- lead time ---------------------------------------------------
        days_to_checkin: int | None = (inventory.stay_date - self.today).days
        if days_to_checkin < 0:
            days_to_checkin = None
            missing.append("lead_time")
            notes.append("Stay date is in the past; lead-time signal not applicable.")

        # --- booking pace -------------------------------------------------
        expected = self.expected_pickup_per_week * (self.pace_lookback_days / 7.0)
        recent = self._pickup.get((inventory.room_id, inventory.stay_date))
        pace_index: float | None = None
        if recent is None:
            # No booking rows at all for this room -> genuinely no pace signal.
            if not self._has_any_bookings(inventory.room_id):
                missing.append("booking_pace")
            else:
                recent = 0.0
        if recent is not None and expected > 0:
            pace_index = round(recent / expected, 4)

        # --- calendar ------------------------------------------------------
        weekday = inventory.stay_date.weekday()
        day_name = WEEKDAY_NAMES[weekday]
        month = inventory.stay_date.month
        season_label = inventory.season or self.season_labels.get(str(month))

        # --- history --------------------------------------------------------
        hist = self._historical.get((inventory.room_id, weekday))
        hist_occ = inventory.historical_occupancy
        hist_price = inventory.historical_avg_price
        if hist_occ is None and hist:
            hist_occ = hist[0]
        if hist_price is None and hist:
            hist_price = hist[1]
        if hist_occ is None:
            missing.append("historical_occupancy")

        # --- market ----------------------------------------------------------
        observations = self._market_by_key.get((inventory.room_id, inventory.stay_date), [])
        market_reference: float | None = None
        market_index: float | None = None
        baseline = self._market_baseline.get(inventory.room_id)
        sources: tuple[str, ...] = ()
        if observations:
            market_reference = round(
                statistics.median([o.observed_price for o in observations]), 2
            )
            sources = tuple(sorted({o.source for o in observations}))
            if baseline:
                market_index = round(market_reference / baseline, 4)
        if market_index is None:
            missing.append("market")

        return PricingContext(
            property_id=prop.id if prop else 0,
            property_name=prop.name if prop else "Unknown property",
            room_id=room.id if room else inventory.room_id,
            room_name=room.name if room else "Unknown room",
            room_type=room.room_type if room else "",
            stay_date=inventory.stay_date,
            currency=prop.currency if prop else "VND",
            base_price=room.base_price if room else inventory.current_price,
            current_price=inventory.current_price,
            min_price=room.min_price if room else None,
            max_price=room.max_price if room else None,
            units_total=inventory.units_total,
            units_sold=inventory.units_sold,
            occupancy=occupancy,
            days_to_checkin=days_to_checkin,
            avg_booking_lead_time=self._avg_lead_time.get(inventory.room_id),
            recent_pickup=recent,
            expected_pickup=round(expected, 4),
            booking_pace_index=pace_index,
            historical_occupancy=hist_occ,
            historical_avg_price=hist_price,
            day_of_week=day_name,
            is_weekend=weekday >= 4,  # Fri/Sat/Sun priced as weekend for STR. A20
            month=month,
            season_label=season_label,
            is_event=bool(inventory.is_event),
            event_name=inventory.event_name,
            market_reference_price=market_reference,
            market_baseline_price=round(baseline, 2) if baseline else None,
            market_price_index=market_index,
            market_observation_count=len(observations),
            market_sources=sources,
            missing=tuple(missing),
            notes=tuple(notes),
        )

    def build_many(self, inventories: list[StayDateInventory]) -> list[PricingContext]:
        if not self._loaded:
            self.prepare()
        return [self.build(inv) for inv in inventories]

    # ---------------------------------------------------------------- helper
    def _has_any_bookings(self, room_id: int) -> bool:
        return room_id in self._avg_lead_time
