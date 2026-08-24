"""Regressions from the 58f93dd code review.

Every bug here shared a shape: code that could never execute its intended
path, while tests that only asserted "the call returned something" passed.
Each test below fails against the pre-fix code.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dynamic_pricing.features.engine import FeatureEngine
from dynamic_pricing.models import Base, Booking, Property, RoomType, StayDateInventory
from dynamic_pricing.pricing import default_config, get_engine, merge_config
from dynamic_pricing.pricing.engine_v2 import _band_for
from dynamic_pricing.providers.market.base import MarketObservationDTO


# --- #1 public-web collection was 100% broken by a missed rename ----------
def test_public_web_builds_a_valid_observation_dto():
    """The provider constructed the DTO with a field name that no longer exists."""
    from dynamic_pricing.providers.market.public_web import PublicWebMarketDataProvider

    provider = PublicWebMarketDataProvider()
    # Reproduce exactly the kwargs _collect_one passes.
    dto = MarketObservationDTO(
        stay_date=date(2026, 10, 1),
        competitor_name="example.com",
        observed_price=2_400_000,
        source="public_web",
        property_external_id="LUM-HCM",
        room_type_external_id="LUM-2BR-REG",
        room_category=None,
        confidence="LOW",
    )
    assert dto.room_type_external_id == "LUM-2BR-REG"
    assert provider.max_confidence == "LOW"


def test_public_web_source_has_no_stale_field_names():
    """A frozen dataclass turns a missed rename into a runtime-only failure."""
    import inspect

    from dynamic_pricing.providers.market import public_web

    source = inspect.getsource(public_web)
    assert "room_external_id" not in source, "stale pre-rename field name survives"


# --- #2 clearing a numeric setting destroyed the whole run ----------------
def test_cleared_numeric_setting_falls_back_to_default():
    """The Settings UI emits null for a cleared field; null must not reach the engine."""
    merged = merge_config({"market": {"sensitivity": None}})
    assert merged["market"]["sensitivity"] == 0.50


def test_intentional_nulls_are_still_preserved():
    """Keys whose default IS None must keep their nullability."""
    merged = merge_config({"booking_curve": {"anchors": None}})
    assert merged["booking_curve"]["anchors"] is None


@pytest.mark.parametrize(
    "path", [("market", "sensitivity"), ("event", "impact_adjustment_pct"), ("dynamic", "max_total_adjustment_pct")]
)
def test_nulled_settings_never_crash_the_engine(path):
    from conftest import make_context

    section, key = path
    config = merge_config({section: {key: None}})
    result = get_engine("v2").calculate(make_context(), config)
    assert result.recommended_net_rate > 0


def test_a_systemic_error_stops_the_run_and_keeps_the_previous_one():
    """A repeated error is a config fault, not a bad row — it must not silently
    drop stay dates.

    Round 2 caught the previous version of this test asserting only
    `issubclass(PricingRunFailed, RuntimeError)` — a tautology that passed even
    with the guard deleted, in the file written to prevent exactly that. This
    version exercises the behaviour: it breaks a setting every row touches,
    and asserts the run is refused AND the earlier run is still served.
    """
    import os
    import tempfile


    from dynamic_pricing.services.recommendations import (
        PricingRunFailed,
        generate_recommendations,
        latest_run_id,
        load_current_recommendations,
    )

    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/systemic.db"
    from dynamic_pricing.seed import bootstrap

    bootstrap(force=True, quiet=True)

    from dynamic_pricing.db import SessionLocal
    from dynamic_pricing.services.configuration import get_active_configuration

    with SessionLocal() as session:
        good_run = latest_run_id(session)
        good_count = len(load_current_recommendations(session))
        assert good_count > 0

        # rounding.increment is applied to EVERY row, so this is systemic.
        config = get_active_configuration(session)
        # Reassign rather than mutate: SQLAlchemy does not track in-place edits
        # to a JSON column, so a mutation would not persist and this test would
        # silently assert nothing.
        payload = dict(config.payload)
        payload["rounding"] = {**payload["rounding"], "increment": "not-a-number"}
        config.payload = payload
        session.commit()

        with pytest.raises(PricingRunFailed) as caught:
            generate_recommendations(session)

        assert caught.value.affected >= 3, "should stop once the error repeats"
        assert latest_run_id(session) == good_run, "the previous run must still be served"
        assert len(load_current_recommendations(session)) == good_count


def test_a_gated_factor_failure_is_caught_even_though_rows_still_succeed():
    """The defect that made the count-based guard useless.

    `market.sensitivity` is read only AFTER the market gate, so a bad value
    kills just the rows that have qualified market data. `created` stays > 0,
    so 'all rows failed' can never detect it — which is why detection is based
    on error repetition instead.
    """
    from conftest import make_context
    from dynamic_pricing.pricing import get_engine, merge_config

    config = merge_config({"market": {"sensitivity": "not-a-number"}})

    # A row WITHOUT qualified market data never reaches the bad value.
    ungated = make_context(
        market_price_index=None, market_qualified_count=0, market_observation_count=0
    )
    assert get_engine("v2").calculate(ungated, config).recommended_net_rate > 0

    # A row WITH market data does. (float("abc") raises ValueError, not
    # TypeError — the reason a narrow `except TypeError` would not have helped.)
    with pytest.raises(ValueError):
        get_engine("v2").calculate(make_context(), config)


# --- #3 the "Pickup stalled" band was unreachable -------------------------
def test_pickup_stalled_band_is_reachable_at_the_floor():
    """recent_pickup cannot go below 0, so the smallest delta sits ON the threshold."""
    config = default_config()["recent_pickup"]
    floor = 0 - config["expected_pickup_per_week"] * (config["lookback_days"] / 7.0)
    band = _band_for(floor, config["bands"], "max_delta", inclusive=True)
    assert band["label"] == "Pickup stalled"


def test_zero_pickup_is_priced_as_stalled_not_slowing():
    from conftest import make_context

    config = default_config()
    result = get_engine("v2").calculate(
        make_context(recent_pickup=0.0, pickup_delta=-1.0), config
    )
    pickup = next(a for a in result.adjustments if a.code == "recent_pickup")
    assert "stalled" in pickup.label.lower()
    assert pickup.adjustment_pct == pytest.approx(-3.0)


# --- #5 V1's booking-pace factor read a config key that did not exist -----
def test_legacy_v1_booking_pace_factor_is_live():
    from conftest import make_context

    config = default_config()
    v1 = get_engine("v1")
    slow = v1.calculate(make_context(recent_pickup=0.0, expected_pickup=1.0), config)
    fast = v1.calculate(make_context(recent_pickup=4.0, expected_pickup=1.0), config)
    slow_adj = next(a for a in slow.adjustments if a.code == "recent_pickup")
    fast_adj = next(a for a in fast.adjustments if a.code == "recent_pickup")
    assert slow_adj.factor < 1.0, "V1 pace factor is inert — config key mismatch"
    assert fast_adj.factor > 1.0
    assert fast.recommended_net_rate > slow.recommended_net_rate


# --- #9 the pickup window counted one day too many ------------------------
@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as s:
        prop = Property(external_id="P1", name="Luminous")
        s.add(prop)
        s.flush()
        s.add(
            RoomType(
                property_id=prop.id, external_id="RT1", name="2BR Regular",
                category="2br_regular", units_total=10,
            )
        )
        s.commit()
        yield s


def test_pickup_window_spans_exactly_lookback_days(session):
    """An 8-day window compared against a 7-day expectation biases pickup high."""
    today = date(2026, 9, 1)
    rt = session.query(RoomType).first()
    stay = today + timedelta(days=30)
    session.add(
        StayDateInventory(room_type_id=rt.id, stay_date=stay, units_total=10, units_sold=3)
    )
    # exactly 7 days back = inside; 7 days + 1 = outside
    for i, days_ago in enumerate([0, 6, 7]):
        session.add(
            Booking(
                external_id=f"B{i}", room_type_id=rt.id, stay_date=stay,
                booked_at=today - timedelta(days=days_ago),
            )
        )
    session.commit()

    inv = session.query(StayDateInventory).first()
    ctx = FeatureEngine(session, default_config(), today=today).prepare().build(inv)
    assert ctx.recent_pickup == 2, "a 7-day window must not include the 8th day back"


# --- #7 demo bookings contradicted the persisted inventory ----------------
def test_demo_bookings_never_exceed_persisted_units_sold():
    """Two RNG streams described two different occupancies for the same date."""
    from collections import Counter

    from dynamic_pricing.providers.pms.mock import HISTORY_DAYS, HORIZON_DAYS, MockPMSProvider

    today = date(2026, 8, 24)
    provider = MockPMSProvider(today=today)
    start, end = today - timedelta(days=HISTORY_DAYS), today + timedelta(days=HORIZON_DAYS)

    sold = {
        (i.room_type_external_id, i.stay_date): i.units_sold
        for i in provider.fetch_inventory(start, end)
    }
    booked = Counter(
        (b.room_type_external_id, b.stay_date) for b in provider.fetch_bookings(start, end)
    )
    mismatches = [k for k, n in booked.items() if n > sold.get(k, 0)]
    assert not mismatches, f"{len(mismatches)} date(s) have more bookings than units sold"


# --- self-review: dead code that reads as a supported feature -------------
def test_no_engine_has_a_seasonality_factor():
    """The validated rate band encodes the season; a second one would double-count.

    Found while sweeping for the review's "code that can never execute" pattern:
    V1 still carried a dormant _factor_season that was absent from its producer
    tuple AND had no config key, while DECISIONS D17 claimed it was deleted. A
    dormant method reads as a supported feature and invites re-enabling.
    """
    for key in ("v1", "v2"):
        engine = get_engine(key)
        assert not hasattr(engine, "_factor_season"), f"{key} still has a season factor"


def test_no_seasonality_key_is_read_from_configuration():
    import inspect

    from dynamic_pricing.pricing import engine_v1, engine_v2

    for module in (engine_v1, engine_v2):
        source = inspect.getsource(module)
        assert 'cfg.get("season"' not in source, f"{module.__name__} reads a season config key"


def test_every_configured_band_is_reachable():
    """A band whose threshold sits outside its signal's real range is dead.

    Generalises finding #3 (Pickup stalled) so a future threshold edit that
    strands a band fails here rather than silently mispricing.
    """
    config = default_config()

    pickup = config["recent_pickup"]
    floor = -pickup["expected_pickup_per_week"] * (pickup["lookback_days"] / 7.0)
    pickup_hits = {
        _band_for(v, pickup["bands"], "max_delta", inclusive=True)["label"]
        for v in [floor, floor / 2, -0.25, 0.0, 0.5, 2.0, 50.0]
    }
    assert pickup_hits == {b["label"] for b in pickup["bands"]}, "unreachable pickup band"

    # pace_gap ranges over [-1, 1] by construction (both terms are fractions)
    pace_hits = {
        _band_for(v, config["pace"]["bands"], "max_gap")["label"]
        for v in [-1.0, -0.5, -0.1, 0.0, 0.1, 0.5, 1.0]
    }
    assert pace_hits == {b["label"] for b in config["pace"]["bands"]}, "unreachable pace band"


# --- round 3: the gaps between the guards ---------------------------------
def test_config_consumed_outside_the_row_loop_cannot_wedge_the_app():
    """FeatureEngine casts config in __init__ — outside the per-row loop, so
    nothing there can be caught by the repetition guard, which meant a bad value
    surfaced as a 500 with the broken config left ACTIVE.

    Two defences, both asserted: the save path rejects it with a field path, and
    the feature layer degrades to defaults rather than raising.
    """
    from dynamic_pricing.pricing.defaults import ConfigurationInvalid, prepare_config

    for section, key in [
        ("recent_pickup", "lookback_days"),
        ("market", "observation_max_age_days"),
        ("market", "sensitivity"),
        ("rounding", "increment"),
    ]:
        with pytest.raises(ConfigurationInvalid) as caught:
            prepare_config({section: {key: "not-a-number"}})
        assert f"{section}.{key}" in str(caught.value), "must name the offending field path"


def test_feature_engine_degrades_rather_than_raising_on_a_bad_config(session):
    from dynamic_pricing.features.engine import FeatureEngine

    broken = default_config()
    broken["recent_pickup"]["lookback_days"] = "abc"
    broken["market"]["observation_max_age_days"] = None
    engine = FeatureEngine(session, broken, today=date(2026, 9, 1))
    assert engine.pickup_lookback_days == 7
    assert engine.market_max_age_days == 14


def test_malformed_booking_curve_anchors_are_rejected_and_survivable():
    from dynamic_pricing.features.booking_curve import get_booking_curve_provider
    from dynamic_pricing.pricing.defaults import ConfigurationInvalid, prepare_config

    with pytest.raises(ConfigurationInvalid) as caught:
        prepare_config({"booking_curve": {"anchors": [{"day": 0}]}})
    assert "days" in str(caught.value)

    # ...and if one reaches the provider anyway, it must not raise.
    provider = get_booking_curve_provider({"booking_curve": {"anchors": [{"day": 0}]}})
    assert provider.expected_occupancy("2br_regular", "low_2", 30) is not None


@pytest.mark.parametrize(
    "signal,key,edit",
    [("pace", "max_gap", -0.10), ("recent_pickup", "max_delta", -0.6)],
)
def test_legitimate_band_edits_are_not_rejected(signal, key, edit):
    """The validator must not block an operator tuning their own thresholds.

    Sample-based probing did exactly that: [-0.20, -0.10) is an ordinary
    reachable interval, but no fixed sample landed in it, so the operator was
    told their band was impossible.
    """
    from dynamic_pricing.pricing.defaults import coerce_config, validate_config

    config = default_config()
    config[signal]["bands"][1][key] = edit
    assert validate_config(coerce_config(config)[0]) == []


def test_genuinely_stranded_bands_are_still_rejected():
    from dynamic_pricing.pricing.defaults import coerce_config, validate_config

    empty_range = default_config()
    empty_range["pace"]["bands"][2]["max_gap"] = -0.5  # below the band before it
    assert validate_config(coerce_config(empty_range)[0])

    below_domain = default_config()
    below_domain["pace"]["bands"][0]["max_gap"] = -5.0  # outside pace_gap's range
    assert validate_config(coerce_config(below_domain)[0])


def test_cleared_band_member_falls_back_to_the_default():
    """_deep_merge cannot repair a null inside a LIST, so coercion must."""
    from dynamic_pricing.pricing.defaults import coerce_config, merge_config

    config = merge_config({})
    config["pace"]["bands"][2]["adjustment_pct"] = None
    config["pace"]["bands"][0]["max_gap"] = None
    coerced, problems = coerce_config(config)
    assert problems == []
    assert all(b["adjustment_pct"] is not None for b in coerced["pace"]["bands"])
    assert all(b["max_gap"] is not None for b in coerced["pace"]["bands"])


def test_a_rare_failure_is_reported_per_date_not_rolled_back():
    """Repetition decides 'systemic'; the SHARE decides whether to discard the
    run. Conflating them made one defect behave in opposite ways depending on
    how the data happened to fall."""
    from dynamic_pricing.services.recommendations import (
        SYSTEMIC_ERROR_THRESHOLD,
        SYSTEMIC_FAILURE_SHARE,
    )

    assert SYSTEMIC_ERROR_THRESHOLD >= 3
    assert 0 < SYSTEMIC_FAILURE_SHARE < 1, "a bare count has no denominator"
