"""FeatureEngine: measurement correctness and graceful degradation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dynamic_pricing.features.engine import FeatureEngine
from dynamic_pricing.models import (
    Base,
    Booking,
    MarketObservation,
    Property,
    Room,
    StayDateInventory,
)
from dynamic_pricing.pricing import default_config

TODAY = date(2026, 9, 1)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, future=True)
    with maker() as s:
        prop = Property(external_id="P1", name="Test Property", currency="VND")
        s.add(prop)
        s.flush()
        room = Room(
            property_id=prop.id,
            external_id="R1",
            name="Test Room",
            room_type="Studio",
            units_total=10,
            base_price=1_000_000,
            min_price=500_000,
            max_price=3_000_000,
        )
        s.add(room)
        s.flush()
        s.commit()
        yield s


def add_inventory(session, stay_date, sold=5, total=10, price=1_000_000, **kwargs):
    room = session.query(Room).first()
    inv = StayDateInventory(
        room_id=room.id,
        stay_date=stay_date,
        units_total=total,
        units_sold=sold,
        current_price=price,
        **kwargs,
    )
    session.add(inv)
    session.commit()
    return inv


def build(session, inv):
    return FeatureEngine(session, default_config(), today=TODAY).prepare().build(inv)


# ---------------------------------------------------------------- occupancy
def test_occupancy_is_sold_over_total(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=10), sold=7, total=10))
    assert ctx.occupancy == pytest.approx(0.7)
    assert ctx.units_sold == 7 and ctx.units_total == 10


def test_zero_units_total_does_not_divide_by_zero(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=10), sold=0, total=0))
    assert ctx.occupancy is None
    assert ctx.is_missing("occupancy")


# ---------------------------------------------------------------- lead time
def test_days_to_checkin_is_measured_from_today(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=14)))
    assert ctx.days_to_checkin == 14


def test_past_stay_date_marks_lead_time_missing(session):
    ctx = build(session, add_inventory(session, TODAY - timedelta(days=3)))
    assert ctx.days_to_checkin is None
    assert ctx.is_missing("lead_time")


# -------------------------------------------------------------- booking pace
def test_booking_pace_counts_only_the_lookback_window(session):
    room = session.query(Room).first()
    stay = TODAY + timedelta(days=20)
    inv = add_inventory(session, stay)
    # two recent bookings (inside the 7-day window) + one old one
    for i, booked in enumerate([TODAY - timedelta(days=1), TODAY - timedelta(days=5), TODAY - timedelta(days=40)]):
        session.add(
            Booking(external_id=f"B{i}", room_id=room.id, stay_date=stay, booked_at=booked, price=1_000_000)
        )
    session.commit()
    ctx = build(session, inv)
    assert ctx.recent_pickup == 2
    assert ctx.booking_pace_index == pytest.approx(2.0)


def test_pace_is_missing_when_the_room_has_no_bookings_at_all(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=20)))
    assert ctx.is_missing("booking_pace")
    assert ctx.booking_pace_index is None


def test_pace_is_zero_not_missing_when_other_dates_have_bookings(session):
    room = session.query(Room).first()
    other = TODAY + timedelta(days=5)
    session.add(
        Booking(external_id="B1", room_id=room.id, stay_date=other, booked_at=TODAY, price=1_000_000)
    )
    session.commit()
    quiet = add_inventory(session, TODAY + timedelta(days=25))
    ctx = build(session, quiet)
    assert ctx.booking_pace_index == pytest.approx(0.0)
    assert not ctx.is_missing("booking_pace")


# ------------------------------------------------------------------ calendar
@pytest.mark.parametrize(
    "stay,expected_day,weekend",
    [
        (date(2026, 9, 7), "monday", False),
        (date(2026, 9, 11), "friday", True),
        (date(2026, 9, 12), "saturday", True),
        (date(2026, 9, 13), "sunday", True),
    ],
)
def test_day_of_week_and_weekend_flag(session, stay, expected_day, weekend):
    ctx = build(session, add_inventory(session, stay))
    assert ctx.day_of_week == expected_day
    assert ctx.is_weekend is weekend


def test_event_flag_is_carried_through(session):
    inv = add_inventory(
        session, TODAY + timedelta(days=10), is_event=True, event_name="Mid-Autumn Festival"
    )
    ctx = build(session, inv)
    assert ctx.is_event is True
    assert ctx.event_name == "Mid-Autumn Festival"


# -------------------------------------------------------------------- market
def test_market_index_is_reference_over_baseline(session):
    room = session.query(Room).first()
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    # baseline across the horizon = median of all observations for the room
    for offset, price in [(10, 1_200_000), (11, 1_000_000), (12, 1_000_000)]:
        session.add(
            MarketObservation(
                property_id=room.property_id,
                room_id=room.id,
                stay_date=TODAY + timedelta(days=offset),
                competitor_name="Comp",
                observed_price=price,
                source="mock",
            )
        )
    session.commit()
    ctx = build(session, inv)
    assert ctx.market_reference_price == pytest.approx(1_200_000)
    assert ctx.market_baseline_price == pytest.approx(1_000_000)
    assert ctx.market_price_index == pytest.approx(1.2)
    assert ctx.market_observation_count == 1


def test_missing_market_observations_flagged(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=10)))
    assert ctx.market_price_index is None
    assert ctx.is_missing("market")
    assert ctx.market_observation_count == 0


def test_stale_observations_are_ignored(session):
    from datetime import datetime, timedelta as td

    room = session.query(Room).first()
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    session.add(
        MarketObservation(
            property_id=room.property_id,
            room_id=room.id,
            stay_date=stay,
            competitor_name="Stale Comp",
            observed_price=2_000_000,
            source="mock",
            collected_at=datetime.now() - td(days=60),
        )
    )
    session.commit()
    ctx = build(session, inv)
    assert ctx.market_observation_count == 0
    assert ctx.is_missing("market")


def test_property_level_observation_applies_to_its_rooms(session):
    room = session.query(Room).first()
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    session.add(
        MarketObservation(
            property_id=room.property_id,
            room_id=None,  # property-wide reference
            stay_date=stay,
            competitor_name="Neighbourhood average",
            observed_price=1_500_000,
            source="manual",
        )
    )
    session.commit()
    ctx = build(session, inv)
    assert ctx.market_observation_count == 1
    assert ctx.market_reference_price == pytest.approx(1_500_000)


# ---------------------------------------------------------------- provenance
def test_context_serialises_for_persistence(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=10)))
    payload = ctx.to_dict()
    assert payload["room_name"] == "Test Room"
    assert payload["stay_date"] == (TODAY + timedelta(days=10)).isoformat()
    assert isinstance(payload["missing"], list)


def test_engine_reuses_one_prepared_instance_for_many_rows(session):
    rows = [add_inventory(session, TODAY + timedelta(days=d)) for d in range(1, 6)]
    fe = FeatureEngine(session, default_config(), today=TODAY).prepare()
    contexts = fe.build_many(rows)
    assert len(contexts) == 5
    assert [c.days_to_checkin for c in contexts] == [1, 2, 3, 4, 5]
