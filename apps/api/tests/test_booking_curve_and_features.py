"""BookingCurveProvider and the FeatureEngine's pace/confidence logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dynamic_pricing.features.booking_curve import (
    MAX_EXPECTED_OCCUPANCY,
    DemoBookingCurveProvider,
    HistoricalBookingCurveProvider,
    get_booking_curve_provider,
)
from dynamic_pricing.features.engine import FeatureEngine
from dynamic_pricing.models import (
    Base,
    Booking,
    Event,
    MarketObservation,
    PhysicalRoom,
    Property,
    RoomType,
    StayDateInventory,
)
from dynamic_pricing.pricing import default_config

TODAY = date(2026, 9, 1)


# ------------------------------------------------------------ booking curve
def test_expected_occupancy_decreases_with_lead_time():
    curve = DemoBookingCurveProvider()
    values = [curve.expected_occupancy("2br_regular", "low_2", d) for d in [0, 7, 30, 60, 90]]
    assert values == sorted(values, reverse=True), "curve must decline as the date gets further out"


def test_curve_never_expects_a_full_house_on_arrival_day():
    """A 22-unit building is not expected to be 100% sold at D-0."""
    curve = DemoBookingCurveProvider()
    for season in ["low_1", "low_2", "medium", "high_1", "high_2"]:
        for category in ["2br_regular", "2br_premium", "3br"]:
            assert curve.expected_occupancy(category, season, 0) <= MAX_EXPECTED_OCCUPANCY


def test_curve_is_bounded_between_zero_and_one():
    curve = DemoBookingCurveProvider()
    for d in [0, 1, 5, 45, 200, 900]:
        v = curve.expected_occupancy("3br", "high_2", d)
        assert 0.0 <= v <= 1.0


def test_high_season_books_earlier_than_low_season():
    curve = DemoBookingCurveProvider()
    high = curve.expected_occupancy("2br_regular", "high_2", 30)
    low = curve.expected_occupancy("2br_regular", "low_1", 30)
    assert high > low


def test_curve_is_deterministic():
    a = DemoBookingCurveProvider().expected_occupancy("3br", "medium", 21)
    b = DemoBookingCurveProvider().expected_occupancy("3br", "medium", 21)
    assert a == b


def test_demo_curve_is_flagged_unvalidated():
    assert DemoBookingCurveProvider().validated is False


def test_negative_lead_time_has_no_expectation():
    assert DemoBookingCurveProvider().expected_occupancy("3br", "medium", -5) is None


def test_historical_provider_is_a_documented_placeholder():
    """It must return None, so pace goes neutral rather than silently wrong."""
    provider = HistoricalBookingCurveProvider()
    assert provider.validated is True
    assert provider.expected_occupancy("2br_regular", "low_2", 30) is None


def test_provider_selection_from_config():
    assert isinstance(get_booking_curve_provider({}), DemoBookingCurveProvider)
    assert isinstance(
        get_booking_curve_provider({"booking_curve": {"provider": "historical"}}),
        HistoricalBookingCurveProvider,
    )


# ------------------------------------------------------------ feature engine
@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as s:
        prop = Property(external_id="P1", name="Luminous", currency="VND")
        s.add(prop)
        s.flush()
        rt = RoomType(
            property_id=prop.id, external_id="RT1", name="2BR Regular",
            category="2br_regular", capacity=4, units_total=10,
        )
        s.add(rt)
        s.flush()
        for i in range(10):
            s.add(PhysicalRoom(room_type_id=rt.id, external_id=f"U{i}", unit_label=f"A-{i}"))
        s.commit()
        yield s


def add_inventory(session, stay_date, sold=4, total=10, net_rate=2_100_000, **kw):
    rt = session.query(RoomType).first()
    inv = StayDateInventory(
        room_type_id=rt.id, stay_date=stay_date, units_total=total,
        units_sold=sold, current_net_rate=net_rate, **kw,
    )
    session.add(inv)
    session.commit()
    return inv


def build(session, inv, config=None):
    return FeatureEngine(session, config or default_config(), today=TODAY).prepare().build(inv)


def test_rate_band_is_resolved_from_the_validated_book(session):
    ctx = build(session, add_inventory(session, date(2026, 9, 20)))
    assert ctx.season_key == "low_2"
    assert ctx.band_min_net_rate == 1_800_000
    assert ctx.band_base_net_rate == 2_100_000
    assert ctx.band_max_net_rate == 2_300_000
    assert ctx.rate_band_source == "CLIENT_VALIDATED"


def test_pace_gap_is_actual_minus_expected(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=30), sold=7))
    assert ctx.occupancy == pytest.approx(0.7)
    assert ctx.expected_occupancy is not None
    assert ctx.pace_gap == pytest.approx(round(0.7 - ctx.expected_occupancy, 4))


def test_pace_gap_sign_reflects_ahead_or_behind(session):
    ahead = build(session, add_inventory(session, TODAY + timedelta(days=60), sold=9))
    session.query(StayDateInventory).delete()
    session.commit()
    behind = build(session, add_inventory(session, TODAY + timedelta(days=2), sold=1))
    assert ahead.pace_gap > 0
    assert behind.pace_gap < 0


def test_days_to_arrival_measured_from_today(session):
    assert build(session, add_inventory(session, TODAY + timedelta(days=14))).days_to_arrival == 14


def test_past_stay_date_has_no_forward_signals(session):
    ctx = build(session, add_inventory(session, TODAY - timedelta(days=3)))
    assert ctx.days_to_arrival is None
    assert ctx.pace_gap is None
    assert ctx.is_missing("pace_gap")


def test_recent_pickup_counts_only_the_lookback_window(session):
    rt = session.query(RoomType).first()
    stay = TODAY + timedelta(days=20)
    inv = add_inventory(session, stay)
    for i, booked in enumerate(
        [TODAY - timedelta(days=1), TODAY - timedelta(days=4), TODAY - timedelta(days=40)]
    ):
        session.add(
            Booking(external_id=f"B{i}", room_type_id=rt.id, stay_date=stay, booked_at=booked)
        )
    session.commit()
    ctx = build(session, inv)
    assert ctx.recent_pickup == 2
    assert ctx.pickup_delta == pytest.approx(1.0)


def test_pickup_missing_when_room_type_has_no_bookings(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=20)))
    assert ctx.is_missing("recent_pickup")
    assert ctx.pickup_delta is None


def test_event_is_attached_to_covered_stay_dates(session):
    stay = TODAY + timedelta(days=10)
    session.add(
        Event(
            name="HCMC Marathon", start_date=stay - timedelta(days=1),
            end_date=stay + timedelta(days=1), impact_level="high", event_type="sport",
        )
    )
    session.commit()
    ctx = build(session, add_inventory(session, stay))
    assert ctx.is_event is True
    assert ctx.event_name == "HCMC Marathon"
    assert ctx.event_impact_level == "high"


def test_inactive_event_is_ignored(session):
    stay = TODAY + timedelta(days=10)
    session.add(
        Event(name="Cancelled", start_date=stay, end_date=stay, is_active=False)
    )
    session.commit()
    assert build(session, add_inventory(session, stay)).is_event is False


# --------------------------------------------------- market confidence gate
def _observation(session, stay, price, confidence, **kw):
    rt = session.query(RoomType).first()
    session.add(
        MarketObservation(
            property_id=rt.property_id, room_type_id=rt.id, stay_date=stay,
            competitor_name=kw.pop("name", "Comp"), observed_price=price,
            confidence=confidence, source=kw.pop("source", "manual"), **kw,
        )
    )
    session.commit()


def test_low_confidence_observations_are_counted_but_not_used(session):
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    for i in range(3):
        _observation(session, stay, 2_500_000, "LOW", name=f"C{i}")
    ctx = build(session, inv)
    assert ctx.market_observation_count == 3
    assert ctx.market_qualified_count == 0
    assert ctx.market_ignored_count == 3
    assert ctx.market_price_index is None
    assert ctx.is_missing("market")


def test_high_confidence_observations_produce_a_market_index(session):
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    _observation(session, stay, 2_400_000, "HIGH", name="C1")
    _observation(session, stay, 2_400_000, "HIGH", name="C2")
    _observation(session, stay + timedelta(days=1), 2_000_000, "HIGH", name="C3")
    ctx = build(session, inv)
    assert ctx.market_qualified_count == 2
    assert ctx.market_reference_net_rate == pytest.approx(2_400_000)
    assert ctx.market_price_index is not None
    assert ctx.market_confidence == "HIGH"


def test_confidence_gate_is_configurable(session):
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    for i in range(2):
        _observation(session, stay, 2_400_000, "LOW", name=f"C{i}")
    config = default_config()
    config["market"]["min_confidence"] = "LOW"
    ctx = build(session, inv, config)
    assert ctx.market_qualified_count == 2, "lowering the gate must admit LOW evidence"


def test_stale_observations_are_ignored(session):
    stay = TODAY + timedelta(days=10)
    inv = add_inventory(session, stay)
    _observation(
        session, stay, 2_400_000, "HIGH",
        observed_at=datetime.now() - timedelta(days=60),
    )
    ctx = build(session, inv)
    assert ctx.market_observation_count == 0
    assert ctx.is_missing("market")


def test_context_serialises_for_reproducibility(session):
    ctx = build(session, add_inventory(session, TODAY + timedelta(days=10)))
    payload = ctx.to_dict()
    assert payload["room_category"] == "2br_regular"
    assert payload["band_base_net_rate"] == 2_100_000
    assert payload["rate_band_source"] == "CLIENT_VALIDATED"
    assert isinstance(payload["missing"], list)
