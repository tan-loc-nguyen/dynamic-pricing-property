"""FeatureEngine — turns normalized operational data into pricing signals.

    Blue Jay / Mock -> normalized rows -> FeatureEngine -> PricingContext -> PricingEngine

This layer owns *measurement* only. It never decides what a measurement is
worth: it computes "occupancy is 78%, expected 64%, so pace gap is +14pp";
the pricing engine decides what that is worth in VND.

Two responsibilities worth calling out:
  * it resolves the CLIENT-VALIDATED rate band for each room type + stay date;
  * it applies the market **confidence gate**, so low-quality observations are
    counted and reported but never silently priced in.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CONFIDENCE_ORDER,
    Booking,
    Event,
    MarketObservation,
    Property,
    RoomType,
    StayDateInventory,
)
from ..pricing.rate_book import CATEGORY_LABELS, NO_BAND_SOURCE, SeasonalRateBook
from .booking_curve import get_booking_curve_provider
from .context import PricingContext

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class FeatureEngine:
    """Builds PricingContexts in bulk with all lookups pre-loaded."""

    def __init__(
        self,
        session: Session,
        config: dict,
        today: date | None = None,
        rate_book: SeasonalRateBook | None = None,
    ) -> None:
        self.session = session
        self.config = config or {}
        self.today = today or date.today()
        self.rate_book = rate_book or SeasonalRateBook()
        self.curve = get_booking_curve_provider(self.config)

        # These casts run OUTSIDE the per-row pricing loop, so anything raising
        # here bypasses the repetition guard, the PricingRunFailed handler and
        # the config rollback -- it surfaces as a 500 with the bad config left
        # active. Saved configs are coerced at the boundary, but this layer also
        # runs against configs that never went through a save, so it degrades to
        # the default rather than trusting its input.
        # Degradations are RECORDED, not just survived. The justification for
        # this layer is configs that never went through a save -- which is
        # exactly when no validator runs, so silently substituting a default
        # would report the fault nowhere at all.
        self.config_degraded: list[str] = []

        def _num(node: dict, key: str, default, kind):
            value = node.get(key)
            if value is None:
                return default
            try:
                return kind(value)
            except (TypeError, ValueError):
                self.config_degraded.append(
                    f"{key}={value!r} is not a number; using {default}."
                )
                return default

        # NOTE: no `or default` here. Coercion guarantees a number, so `or`
        # is no longer defensive -- it is the only thing that could corrupt a
        # legitimate 0. expected_pickup_per_week=0 means "expect no pickup",
        # and silently reading it as 1.0 shifted pickup_delta by a full unit on
        # every row while the UI displayed the 0 the operator saved.
        pickup_cfg = self.config.get("recent_pickup", {}) or {}
        self.pickup_lookback_days = _num(pickup_cfg, "lookback_days", 7, int)
        self.expected_pickup_per_week = _num(pickup_cfg, "expected_pickup_per_week", 1.0, float)

        market_cfg = self.config.get("market", {}) or {}
        self.market_max_age_days = _num(market_cfg, "observation_max_age_days", 14, int)
        confidence = market_cfg.get("min_confidence") or "MEDIUM"
        self.market_min_confidence = str(confidence).upper()

        self._loaded = False
        self._room_types: dict[int, RoomType] = {}
        self._properties: dict[int, Property] = {}
        self._pickup: dict[tuple[int, date], float] = defaultdict(float)
        self._rooms_with_bookings: set[int] = set()
        self._avg_lead_time: dict[int, float] = {}
        self._market_by_key: dict[tuple[int, date], list[MarketObservation]] = defaultdict(list)
        self._market_baseline: dict[int, float] = {}
        self._events: list[Event] = []

    # ------------------------------------------------------------------ load
    def prepare(self) -> "FeatureEngine":
        session = self.session

        self._room_types = {r.id: r for r in session.scalars(select(RoomType)).all()}
        self._properties = {p.id: p for p in session.scalars(select(Property)).all()}
        self._events = list(
            session.scalars(select(Event).where(Event.is_active.is_(True))).all()
        )

        # --- recent pickup, per (room type, stay date) --------------------
        # Inclusive on both ends, so subtract one to count exactly
        # `lookback_days` calendar days -- otherwise an 8-day window is
        # compared against a 7-day expectation and pickup reads high.
        cutoff = self.today - timedelta(days=max(self.pickup_lookback_days - 1, 0))
        bookings = session.scalars(select(Booking).where(Booking.status != "cancelled")).all()

        lead_times: dict[int, list[int]] = defaultdict(list)
        for b in bookings:
            lead_times[b.room_type_id].append(b.lead_time_days)
            self._rooms_with_bookings.add(b.room_type_id)
            if cutoff <= b.booked_at <= self.today:
                self._pickup[(b.room_type_id, b.stay_date)] += 1

        self._avg_lead_time = {
            rid: round(statistics.fmean(v), 2) for rid, v in lead_times.items() if v
        }

        # --- market observations, filtered by freshness -------------------
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_cutoff = now - timedelta(days=self.market_max_age_days)
        observations = session.scalars(select(MarketObservation)).all()

        per_room_prices: dict[int, list[float]] = defaultdict(list)
        rooms_by_property: dict[int, list[int]] = defaultdict(list)
        for rt in self._room_types.values():
            rooms_by_property[rt.property_id].append(rt.id)

        for obs in observations:
            if obs.observed_at and obs.observed_at < age_cutoff:
                continue
            targets = (
                [obs.room_type_id]
                if obs.room_type_id
                else rooms_by_property.get(obs.property_id or -1, [])
            )
            for room_type_id in targets:
                if room_type_id is None:
                    continue
                self._market_by_key[(room_type_id, obs.stay_date)].append(obs)
                # Baseline uses only observations good enough to price on.
                if self._qualifies(obs):
                    per_room_prices[room_type_id].append(obs.observed_price)

        self._market_baseline = {
            rid: statistics.median(p) for rid, p in per_room_prices.items() if p
        }

        self._loaded = True
        return self

    # ---------------------------------------------------------------- helper
    def _qualifies(self, obs: MarketObservation) -> bool:
        """Is this observation good enough to move a price?"""
        return CONFIDENCE_ORDER.get(obs.confidence, 0) >= CONFIDENCE_ORDER.get(
            self.market_min_confidence, 2
        )

    # ----------------------------------------------------------------- build
    def build(self, inventory: StayDateInventory) -> PricingContext:
        if not self._loaded:
            self.prepare()

        room_type = self._room_types.get(inventory.room_type_id) or self.session.get(
            RoomType, inventory.room_type_id
        )
        prop = self._properties.get(room_type.property_id) if room_type else None
        if prop is None and room_type is not None:
            prop = self.session.get(Property, room_type.property_id)

        missing: list[str] = []
        notes: list[str] = []

        # --- validated rate band -----------------------------------------
        band = self.rate_book.lookup(room_type.category, inventory.stay_date) if room_type else None
        if band is None:
            missing.append("rate_band")
            notes.append(
                f"No validated rate band for category '{getattr(room_type, 'category', '?')}' "
                f"in {inventory.stay_date:%B}; falling back to the room type's stored rates."
            )

        # --- occupancy ----------------------------------------------------
        occupancy = inventory.occupancy
        if occupancy is None:
            missing.append("occupancy")

        # --- lead time ----------------------------------------------------
        days_to_arrival: int | None = (inventory.stay_date - self.today).days
        if days_to_arrival < 0:
            days_to_arrival = None
            notes.append("Stay date is in the past; forward-looking signals not applicable.")

        # --- pace position (the primary demand signal) --------------------
        expected_occupancy = None
        pace_gap = None
        if days_to_arrival is not None and room_type is not None:
            expected_occupancy = self.curve.expected_occupancy(
                room_type.category, band.season_key if band else None, days_to_arrival
            )
        if expected_occupancy is None or occupancy is None:
            missing.append("pace_gap")
            if expected_occupancy is None and days_to_arrival is not None:
                notes.append("No booking curve available; pace position could not be computed.")
        else:
            pace_gap = round(occupancy - expected_occupancy, 4)

        # --- recent pickup (acceleration, distinct from pace position) ----
        expected_pickup = self.expected_pickup_per_week * (self.pickup_lookback_days / 7.0)
        recent_pickup = self._pickup.get((inventory.room_type_id, inventory.stay_date))
        pickup_delta = None
        if recent_pickup is None:
            if inventory.room_type_id not in self._rooms_with_bookings:
                missing.append("recent_pickup")
            else:
                recent_pickup = 0.0
        if recent_pickup is not None:
            pickup_delta = round(recent_pickup - expected_pickup, 4)

        # --- calendar ------------------------------------------------------
        weekday = inventory.stay_date.weekday()

        # --- events ---------------------------------------------------------
        event = next(
            (
                e
                for e in self._events
                if e.covers(inventory.stay_date)
                and (e.property_id is None or e.property_id == (prop.id if prop else None))
            ),
            None,
        )

        # --- market, with the confidence gate ------------------------------
        observations = self._market_by_key.get(
            (inventory.room_type_id, inventory.stay_date), []
        )
        qualified = [o for o in observations if self._qualifies(o)]
        ignored = len(observations) - len(qualified)

        market_reference = market_index = None
        market_confidence = None
        baseline = self._market_baseline.get(inventory.room_type_id)
        sources: tuple[str, ...] = tuple(sorted({o.source for o in observations}))

        if qualified:
            market_reference = round(statistics.median([o.observed_price for o in qualified]), 2)
            market_confidence = min(
                (o.confidence for o in qualified), key=lambda c: CONFIDENCE_ORDER.get(c, 0)
            )
            if baseline:
                market_index = round(market_reference / baseline, 4)
        elif observations:
            market_confidence = max(
                (o.confidence for o in observations), key=lambda c: CONFIDENCE_ORDER.get(c, 0)
            )
            notes.append(
                f"{ignored} market observation(s) seen but below the "
                f"{self.market_min_confidence} confidence bar; not used for pricing."
            )

        if market_index is None:
            missing.append("market")

        return PricingContext(
            property_id=prop.id if prop else 0,
            property_name=prop.name if prop else "Unknown property",
            room_type_id=room_type.id if room_type else inventory.room_type_id,
            room_type_name=room_type.name if room_type else "Unknown room type",
            room_category=room_type.category if room_type else "",
            room_category_label=CATEGORY_LABELS.get(
                room_type.category if room_type else "", room_type.name if room_type else ""
            ),
            stay_date=inventory.stay_date,
            currency=prop.currency if prop else "VND",
            season_key=band.season_key if band else None,
            season_label=band.season_label if band else None,
            season_note=band.note if band else None,
            band_min_net_rate=band.min_net_rate if band else (room_type.fallback_min_net_rate if room_type else None),
            band_base_net_rate=band.base_net_rate if band else (room_type.fallback_base_net_rate if room_type else None),
            band_max_net_rate=band.max_net_rate if band else (room_type.fallback_max_net_rate if room_type else None),
            rate_band_source=band.source if band else NO_BAND_SOURCE,
            current_net_rate=inventory.current_net_rate,
            current_ota_price=inventory.current_ota_price,
            rate_provenance=getattr(inventory, "rate_provenance", "published") or "published",
            units_total=inventory.units_total,
            units_sold=inventory.units_sold,
            units_available=inventory.units_available,
            occupancy=occupancy,
            days_to_arrival=days_to_arrival,
            expected_occupancy=expected_occupancy,
            pace_gap=pace_gap,
            booking_curve_source=self.curve.name,
            booking_curve_validated=self.curve.validated,
            recent_pickup=recent_pickup,
            expected_pickup=round(expected_pickup, 4),
            pickup_delta=pickup_delta,
            avg_booking_lead_time=self._avg_lead_time.get(inventory.room_type_id),
            historical_occupancy=inventory.historical_occupancy,
            historical_avg_net_rate=inventory.historical_avg_net_rate,
            day_of_week=WEEKDAY_NAMES[weekday],
            is_weekend=weekday >= 4,
            month=inventory.stay_date.month,
            is_event=event is not None,
            event_name=event.name if event else None,
            event_impact_level=event.impact_level if event else None,
            event_adjustment_pct=event.adjustment_pct if event else None,
            market_reference_net_rate=market_reference,
            market_baseline_net_rate=round(baseline, 2) if baseline else None,
            market_price_index=market_index,
            market_confidence=market_confidence,
            market_observation_count=len(observations),
            market_qualified_count=len(qualified),
            market_ignored_count=ignored,
            market_sources=sources,
            missing=tuple(missing),
            notes=tuple(notes),
        )

    def build_many(self, inventories: list[StayDateInventory]) -> list[PricingContext]:
        if not self._loaded:
            self.prepare()
        return [self.build(inv) for inv in inventories]
