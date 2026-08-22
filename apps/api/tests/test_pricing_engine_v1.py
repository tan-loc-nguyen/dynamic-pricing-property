"""PricingEngineV1 behaviour.

Pricing is the business-critical part of this product, so these tests pin down
each factor in isolation against a neutral baseline.
"""

from __future__ import annotations

from datetime import date

import pytest

from conftest import make_context
from dynamic_pricing.pricing import default_config, get_engine
from dynamic_pricing.pricing.engine_v1 import _round_price


# --------------------------------------------------------------- determinism
def test_identical_inputs_produce_identical_output(engine, neutral_config):
    ctx = make_context()
    first = engine.calculate(ctx, neutral_config)
    second = engine.calculate(ctx, neutral_config)
    assert first.recommended_price == second.recommended_price
    assert [a.factor for a in first.adjustments] == [a.factor for a in second.adjustments]
    assert first.explanation == second.explanation


def test_repeated_runs_are_stable_across_many_iterations(engine, neutral_config):
    ctx = make_context(occupancy=0.9, units_sold=9, booking_pace_index=1.8)
    prices = {engine.calculate(ctx, neutral_config).recommended_price for _ in range(25)}
    assert len(prices) == 1


def test_engine_does_not_mutate_the_configuration(engine, neutral_config):
    import copy

    snapshot = copy.deepcopy(neutral_config)
    engine.calculate(make_context(), neutral_config)
    assert neutral_config == snapshot


# ------------------------------------------------------------------ baseline
def test_neutral_context_returns_base_price(engine, neutral_config):
    result = engine.calculate(make_context(), neutral_config)
    assert result.recommended_price == pytest.approx(1_000_000, abs=1)
    assert result.total_multiplier == pytest.approx(1.0, abs=1e-6)


def test_normal_weekday_is_not_uplifted(engine, neutral_config):
    result = engine.calculate(make_context(day_of_week="tuesday"), neutral_config)
    # Tuesday multiplier is 0.95 in the demo defaults.
    assert result.recommended_price == pytest.approx(950_000, abs=5_000)


# ----------------------------------------------------------------- occupancy
def test_high_occupancy_increases_price(engine, neutral_config):
    low = engine.calculate(make_context(occupancy=0.60, units_sold=6), neutral_config)
    high = engine.calculate(make_context(occupancy=0.80, units_sold=8), neutral_config)
    assert high.recommended_price > low.recommended_price


def test_low_occupancy_decreases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    low = engine.calculate(make_context(occupancy=0.20, units_sold=2), neutral_config)
    assert low.recommended_price < baseline.recommended_price


@pytest.mark.parametrize(
    "occupancy,expected_band",
    [
        (0.10, "Very low occupancy"),
        (0.40, "Low occupancy"),
        (0.60, "Healthy occupancy"),
        (0.80, "High occupancy"),
        (0.95, "Very high occupancy"),
    ],
)
def test_occupancy_bands_are_selected_correctly(engine, neutral_config, occupancy, expected_band):
    result = engine.calculate(make_context(occupancy=occupancy), neutral_config)
    occ = next(a for a in result.adjustments if a.code == "occupancy")
    assert expected_band in occ.label


# -------------------------------------------------------------- booking pace
def test_strong_booking_pace_increases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    strong = engine.calculate(make_context(booking_pace_index=1.6, recent_pickup=2.0), neutral_config)
    assert strong.recommended_price > baseline.recommended_price


def test_weak_booking_pace_decreases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    weak = engine.calculate(make_context(booking_pace_index=0.2, recent_pickup=0.0), neutral_config)
    assert weak.recommended_price < baseline.recommended_price


# ------------------------------------------------------------------ lead time
def test_short_lead_time_reduces_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    # occupancy kept high so the urgency rule does NOT also fire
    short = engine.calculate(make_context(days_to_checkin=2, occupancy=0.80, units_sold=8), neutral_config)
    baseline_high_occ = engine.calculate(make_context(occupancy=0.80, units_sold=8), neutral_config)
    assert short.recommended_price < baseline_high_occ.recommended_price
    assert baseline.recommended_price > 0


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "Last minute"),
        (3, "Last minute"),
        (4, "Short lead time"),
        (7, "Short lead time"),
        (8, "Normal lead time"),
        (30, "Normal lead time"),
        (31, "Long lead time"),
        (90, "Far out"),
    ],
)
def test_lead_time_band_boundaries(engine, neutral_config, days, expected):
    result = engine.calculate(
        make_context(days_to_checkin=days, occupancy=0.80, units_sold=8), neutral_config
    )
    lead = next(a for a in result.adjustments if a.code == "lead_time")
    assert expected in lead.label


def test_urgency_discount_fires_only_when_near_and_empty(engine, neutral_config):
    near_empty = engine.calculate(
        make_context(days_to_checkin=3, occupancy=0.20, units_sold=2), neutral_config
    )
    near_full = engine.calculate(
        make_context(days_to_checkin=3, occupancy=0.80, units_sold=8), neutral_config
    )
    assert any(a.code == "urgency_discount" for a in near_empty.adjustments)
    assert not any(a.code == "urgency_discount" for a in near_full.adjustments)


# -------------------------------------------------------------------- weekend
def test_weekend_is_priced_above_midweek(engine, neutral_config):
    midweek = engine.calculate(make_context(day_of_week="tuesday"), neutral_config)
    saturday = engine.calculate(make_context(day_of_week="saturday"), neutral_config)
    assert saturday.recommended_price > midweek.recommended_price


def test_every_weekday_multiplier_is_applied(engine, neutral_config):
    for day, multiplier in neutral_config["day_of_week"]["multipliers"].items():
        result = engine.calculate(make_context(day_of_week=day), neutral_config)
        dow = next(a for a in result.adjustments if a.code == "day_of_week")
        assert dow.factor == pytest.approx(multiplier)


# ---------------------------------------------------------------------- event
def test_event_multiplier_increases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    event = engine.calculate(make_context(is_event=True, event_name="Test Festival"), neutral_config)
    assert event.recommended_price > baseline.recommended_price
    adj = next(a for a in event.adjustments if a.code == "event")
    assert adj.factor == pytest.approx(neutral_config["event"]["multiplier"])
    assert "Test Festival" in adj.label


def test_no_event_adjustment_when_not_an_event_date(engine, neutral_config):
    result = engine.calculate(make_context(), neutral_config)
    assert not any(a.code == "event" for a in result.adjustments)


# --------------------------------------------------------------------- market
def test_strong_market_increases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    strong = engine.calculate(make_context(market_price_index=1.25), neutral_config)
    assert strong.recommended_price > baseline.recommended_price


def test_weak_market_decreases_price(engine, neutral_config):
    baseline = engine.calculate(make_context(), neutral_config)
    weak = engine.calculate(make_context(market_price_index=0.75), neutral_config)
    assert weak.recommended_price < baseline.recommended_price


def test_market_factor_respects_sensitivity(engine, neutral_config):
    neutral_config["market"]["sensitivity"] = 0.0
    result = engine.calculate(make_context(market_price_index=1.5), neutral_config)
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.factor == pytest.approx(1.0)


def test_market_factor_is_clamped(engine, neutral_config):
    result = engine.calculate(make_context(market_price_index=5.0), neutral_config)
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.factor <= neutral_config["market"]["max_multiplier"] + 1e-9


def test_missing_market_data_applies_neutral_factor_and_says_so(engine, neutral_config):
    result = engine.calculate(
        make_context(market_price_index=None, market_observation_count=0, missing=("market",)),
        neutral_config,
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.factor == 1.0
    assert market.is_neutral
    assert "unavailable" in market.reason.lower()
    assert "market signal unavailable" in result.explanation.lower()


def test_market_ignored_below_minimum_observations(engine, neutral_config):
    neutral_config["market"]["min_observations"] = 3
    result = engine.calculate(
        make_context(market_price_index=1.4, market_observation_count=1), neutral_config
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.factor == 1.0
    assert "minimum" in market.reason.lower()


# ----------------------------------------------------------- missing features
@pytest.mark.parametrize("signal", ["occupancy", "booking_pace", "lead_time", "market"])
def test_missing_signal_never_raises_and_stays_neutral(engine, neutral_config, signal):
    overrides = {
        "occupancy": {"occupancy": None, "units_sold": None},
        "booking_pace": {"booking_pace_index": None, "recent_pickup": None},
        "lead_time": {"days_to_checkin": None},
        "market": {"market_price_index": None, "market_observation_count": 0},
    }[signal]
    result = engine.calculate(make_context(missing=(signal,), **overrides), neutral_config)
    adj = next(a for a in result.adjustments if a.code == signal)
    assert adj.factor == 1.0
    assert adj.is_neutral
    assert result.recommended_price > 0


def test_all_signals_missing_still_returns_base_price(engine, neutral_config):
    result = engine.calculate(
        make_context(
            occupancy=None,
            units_sold=None,
            days_to_checkin=None,
            booking_pace_index=None,
            recent_pickup=None,
            market_price_index=None,
            market_observation_count=0,
            missing=("occupancy", "lead_time", "booking_pace", "market"),
        ),
        neutral_config,
    )
    assert result.recommended_price == pytest.approx(1_000_000, abs=1)


# ------------------------------------------------------------------- bounds
def test_minimum_price_floor_is_enforced(engine, neutral_config):
    ctx = make_context(min_price=1_400_000, day_of_week="tuesday", occupancy=0.10)
    result = engine.calculate(ctx, neutral_config)
    assert result.recommended_price >= 1_400_000
    assert result.metadata["bounds_applied"] == "min"
    assert any(a.code == "min_price_floor" for a in result.adjustments)


def test_maximum_price_cap_is_enforced(engine, neutral_config):
    ctx = make_context(max_price=1_050_000, day_of_week="saturday", occupancy=0.95, is_event=True)
    result = engine.calculate(ctx, neutral_config)
    assert result.recommended_price <= 1_050_000
    assert result.metadata["bounds_applied"] == "max"
    assert any(a.code == "max_price_cap" for a in result.adjustments)


def test_config_overrides_take_precedence_over_room_bounds(engine, neutral_config):
    neutral_config["pricing"]["max_price_override"] = 900_000
    result = engine.calculate(make_context(max_price=9_000_000), neutral_config)
    assert result.recommended_price <= 900_000


def test_rounding_never_breaks_the_floor(engine, neutral_config):
    neutral_config["pricing"]["rounding_increment"] = 100_000
    ctx = make_context(min_price=1_450_000, occupancy=0.10, day_of_week="tuesday")
    result = engine.calculate(ctx, neutral_config)
    assert result.recommended_price >= 1_450_000


def test_rounding_never_breaks_the_cap(engine, neutral_config):
    neutral_config["pricing"]["rounding_increment"] = 100_000
    ctx = make_context(max_price=1_010_000, occupancy=0.95, day_of_week="saturday", is_event=True)
    result = engine.calculate(ctx, neutral_config)
    assert result.recommended_price <= 1_010_000


# ----------------------------------------------------------------- guardrail
def test_compounding_guardrail_caps_extreme_upside(engine, neutral_config):
    neutral_config["event"]["multiplier"] = 3.0
    neutral_config["day_of_week"]["multipliers"]["thursday"] = 2.0
    result = engine.calculate(make_context(is_event=True, max_price=99_000_000), neutral_config)
    limit = neutral_config["pricing"]["global_multiplier_max"]
    assert result.total_multiplier <= limit + 1e-6
    assert result.metadata["guardrail_applied"] is True


def test_compounding_guardrail_limits_extreme_downside(engine, neutral_config):
    neutral_config["occupancy"]["bands"][0]["multiplier"] = 0.2
    neutral_config["day_of_week"]["multipliers"]["thursday"] = 0.5
    result = engine.calculate(make_context(occupancy=0.05, min_price=1), neutral_config)
    limit = neutral_config["pricing"]["global_multiplier_min"]
    assert result.total_multiplier >= limit - 1e-6


# ------------------------------------------------------------------ rounding
@pytest.mark.parametrize(
    "value,increment,mode,expected",
    [
        (1_234_567, 10_000, "nearest", 1_230_000),
        (1_235_001, 10_000, "nearest", 1_240_000),
        (1_234_567, 10_000, "up", 1_240_000),
        (1_234_567, 10_000, "down", 1_230_000),
        (1_234_567, 0, "nearest", 1_234_567),
        (1_500_000, 100_000, "nearest", 1_500_000),
    ],
)
def test_round_price(value, increment, mode, expected):
    assert _round_price(value, increment, mode) == pytest.approx(expected)


def test_recommended_price_lands_on_the_rounding_increment(engine, neutral_config):
    neutral_config["pricing"]["rounding_increment"] = 50_000
    result = engine.calculate(make_context(occupancy=0.83, day_of_week="friday"), neutral_config)
    assert result.recommended_price % 50_000 == pytest.approx(0, abs=1e-6)


# -------------------------------------------------- configuration sensitivity
def test_changing_a_multiplier_changes_the_recommendation(engine, neutral_config):
    before = engine.calculate(make_context(day_of_week="saturday"), neutral_config)
    neutral_config["day_of_week"]["multipliers"]["saturday"] = 1.50
    after = engine.calculate(make_context(day_of_week="saturday"), neutral_config)
    assert after.recommended_price > before.recommended_price


def test_disabling_a_factor_removes_it_from_the_breakdown(engine, neutral_config):
    neutral_config["occupancy"]["enabled"] = False
    result = engine.calculate(make_context(occupancy=0.95), neutral_config)
    assert not any(a.code == "occupancy" for a in result.adjustments)


def test_partial_config_is_merged_with_defaults(engine):
    from dynamic_pricing.pricing import merge_config

    merged = merge_config({"event": {"multiplier": 1.9}})
    assert merged["event"]["multiplier"] == 1.9
    assert merged["day_of_week"]["multipliers"]["saturday"] == 1.15  # default preserved
    result = engine.calculate(make_context(is_event=True), merged)
    assert result.recommended_price > 0


# ----------------------------------------------------------------- explanation
def test_breakdown_is_arithmetically_consistent(engine, neutral_config):
    result = engine.calculate(
        make_context(day_of_week="saturday", occupancy=0.90, booking_pace_index=1.7), neutral_config
    )
    running = result.base_price
    for adj in result.adjustments:
        assert adj.price_before == pytest.approx(running, abs=0.01)
        assert adj.price_after == pytest.approx(adj.price_before * adj.factor, abs=0.01)
        assert adj.delta == pytest.approx(adj.price_after - adj.price_before, abs=0.01)
        running = adj.price_after
    assert result.recommended_price == pytest.approx(running, abs=0.01)


def test_result_reports_change_versus_current_price(engine, neutral_config):
    result = engine.calculate(make_context(current_price=800_000), neutral_config)
    expected = (result.recommended_price - 800_000) / 800_000 * 100
    assert result.change_pct == pytest.approx(expected, abs=0.01)


def test_explanation_mentions_each_applied_factor(engine, neutral_config):
    result = engine.calculate(
        make_context(day_of_week="saturday", occupancy=0.90, is_event=True, event_name="Gala"),
        neutral_config,
    )
    assert "Saturday" in result.explanation
    assert "occupancy" in result.explanation.lower()
    assert "Gala" in result.explanation


def test_metadata_flags_assumptions_as_unvalidated(engine, neutral_config):
    result = engine.calculate(make_context(), neutral_config)
    assert result.metadata["assumptions_status"] == "UNVALIDATED"
    assert result.engine_version == "v1.0.0"
