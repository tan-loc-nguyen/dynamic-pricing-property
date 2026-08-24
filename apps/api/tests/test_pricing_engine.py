"""RateBandPricingEngine — the dynamic layer above the validated rate band."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from conftest import make_context
from dynamic_pricing.pricing.engine import _round_rate


# ---------------------------------------------------------------- anchoring
def test_neutral_context_returns_the_validated_base_rate(engine, config):
    result = engine.calculate(make_context(), config)
    assert result.recommended_net_rate == pytest.approx(2_100_000)  # low_2 2BR Regular BASE
    assert result.base_net_rate == pytest.approx(2_100_000)
    assert result.total_adjustment_pct == pytest.approx(0.0, abs=0.01)


def test_the_band_is_the_first_and_explicit_step(engine, config):
    result = engine.calculate(make_context(), config)
    first = result.adjustments[0]
    assert first.code == "rate_band"
    assert first.label_key == "adjustments.rate_band"
    assert first.params["source"] == "CLIENT_VALIDATED"
    assert first.params["rate_basis"] == "NET"


@pytest.mark.parametrize(
    "stay,category,expected_base",
    [
        (date(2026, 1, 15), "3br", 3_800_000),        # Nov–Jan high season
        (date(2026, 5, 20), "2br_regular", 2_000_000),
        (date(2026, 7, 20), "2br_premium", 2_700_000),
        (date(2026, 3, 5), "3br", 3_200_000),
    ],
)
def test_season_selects_the_band_across_the_year(engine, config, stay, category, expected_base):
    ctx = make_context(stay_date=stay, room_category=category)
    assert engine.calculate(ctx, config).base_net_rate == pytest.approx(expected_base)


def test_seasonality_is_not_applied_twice(engine, config):
    """The band already encodes the season, so there must be no season factor."""
    result = engine.calculate(make_context(), config)
    codes = {a.code for a in result.adjustments}
    assert "season" not in codes
    assert "seasonality" not in codes
    # A neutral context must land exactly on BASE, not on BASE x something.
    assert result.recommended_net_rate == pytest.approx(result.base_net_rate)


def test_no_independent_occupancy_or_lead_time_factor(engine, config):
    """Occupancy and lead time are folded into pace — never priced separately."""
    codes = {a.code for a in engine.calculate(make_context(), config).adjustments}
    assert "occupancy" not in codes
    assert "lead_time" not in codes
    assert "urgency_discount" not in codes


# -------------------------------------------------------------- determinism
def test_identical_inputs_produce_identical_output(engine, config):
    ctx = make_context(pace_gap=0.15, pickup_delta=1.0)
    a, b = engine.calculate(ctx, config), engine.calculate(ctx, config)
    assert a.recommended_net_rate == b.recommended_net_rate
    assert [x.label_key for x in a.adjustments] == [x.label_key for x in b.adjustments]
    assert [x.params for x in a.adjustments] == [x.params for x in b.adjustments]
    assert [x.adjustment_pct for x in a.adjustments] == [x.adjustment_pct for x in b.adjustments]


def test_repeated_runs_are_stable(engine, config):
    ctx = make_context(pace_gap=-0.3, pickup_delta=-2.0)
    assert len({engine.calculate(ctx, config).recommended_net_rate for _ in range(25)}) == 1


def test_engine_does_not_mutate_configuration(engine, config):
    snapshot = copy.deepcopy(config)
    engine.calculate(make_context(), config)
    assert config == snapshot


# ---------------------------------------------------------- pace (primary)
def test_ahead_of_pace_raises_the_rate(engine, config):
    base = engine.calculate(make_context(), config)
    ahead = engine.calculate(make_context(occupancy=0.7, pace_gap=0.30), config)
    assert ahead.recommended_net_rate > base.recommended_net_rate


def test_behind_pace_lowers_the_rate(engine, config):
    base = engine.calculate(make_context(), config)
    behind = engine.calculate(make_context(occupancy=0.1, pace_gap=-0.30), config)
    assert behind.recommended_net_rate < base.recommended_net_rate


@pytest.mark.parametrize(
    "gap,expected_label",
    [
        (-0.40, "Well behind pace"),
        (-0.12, "Behind pace"),
        (0.0, "On pace"),
        (0.12, "Ahead of pace"),
        (0.40, "Well ahead of pace"),
    ],
)
def test_pace_bands_are_selected_correctly(engine, config, gap, expected_label):
    result = engine.calculate(make_context(pace_gap=gap), config)
    pace = next(a for a in result.adjustments if a.code == "pace")
    assert expected_label in pace.label


def test_same_occupancy_prices_differently_at_different_lead_times(engine, config):
    """The whole point of pace position: 30% at D-90 != 30% at D-2."""
    far = engine.calculate(
        make_context(occupancy=0.30, days_to_arrival=90, expected_occupancy=0.11, pace_gap=0.19),
        config,
    )
    near = engine.calculate(
        make_context(occupancy=0.30, days_to_arrival=2, expected_occupancy=0.78, pace_gap=-0.48),
        config,
    )
    assert far.recommended_net_rate > near.recommended_net_rate


def test_missing_pace_is_neutral_and_says_which_signal_is_blind(engine, config):
    result = engine.calculate(
        make_context(pace_gap=None, expected_occupancy=None, missing=("pace_gap",)), config
    )
    pace = next(a for a in result.adjustments if a.code == "pace")
    assert pace.adjustment_pct == 0.0
    assert pace.is_neutral
    assert pace.label_key == "adjustments.pace.unavailable"
    assert result.recommended_net_rate == pytest.approx(result.base_net_rate)


# ------------------------------------------------------------ recent pickup
def test_accelerating_pickup_raises_the_rate(engine, config):
    base = engine.calculate(make_context(), config)
    fast = engine.calculate(make_context(recent_pickup=4.0, pickup_delta=3.0), config)
    assert fast.recommended_net_rate > base.recommended_net_rate


def test_stalled_pickup_lowers_the_rate(engine, config):
    base = engine.calculate(make_context(), config)
    slow = engine.calculate(make_context(recent_pickup=0.0, pickup_delta=-1.5), config)
    assert slow.recommended_net_rate < base.recommended_net_rate


def test_pace_and_pickup_are_separate_signals(engine, config):
    """They measure level vs acceleration and must both appear."""
    result = engine.calculate(make_context(pace_gap=0.3, pickup_delta=3.0), config)
    codes = [a.code for a in result.adjustments]
    assert "pace" in codes and "recent_pickup" in codes
    pace = next(a for a in result.adjustments if a.code == "pace")
    pickup = next(a for a in result.adjustments if a.code == "recent_pickup")
    assert pace.adjustment_pct > 0 and pickup.adjustment_pct > 0
    # pickup is deliberately the smaller lever
    assert abs(pickup.adjustment_pct) < abs(pace.adjustment_pct)


def test_missing_pickup_is_neutral(engine, config):
    result = engine.calculate(
        make_context(pickup_delta=None, recent_pickup=None, missing=("recent_pickup",)), config
    )
    pickup = next(a for a in result.adjustments if a.code == "recent_pickup")
    assert pickup.adjustment_pct == 0.0 and pickup.is_neutral


# -------------------------------------------------------------------- event
def test_event_raises_the_rate_by_impact_level(engine, config):
    base = engine.calculate(make_context(), config)
    low = engine.calculate(
        make_context(is_event=True, event_name="Fair", event_impact_level="low"), config
    )
    high = engine.calculate(
        make_context(is_event=True, event_name="Marathon", event_impact_level="high"), config
    )
    assert base.recommended_net_rate < low.recommended_net_rate < high.recommended_net_rate


def test_event_specific_override_wins_over_impact_level(engine, config):
    result = engine.calculate(
        make_context(
            is_event=True, event_name="Custom", event_impact_level="low", event_adjustment_pct=12.0
        ),
        config,
    )
    event = next(a for a in result.adjustments if a.code == "event")
    assert event.adjustment_pct == pytest.approx(12.0)
    assert event.label_key == "adjustments.event.override"


def test_no_event_step_when_not_an_event_date(engine, config):
    assert not any(a.code == "event" for a in engine.calculate(make_context(), config).adjustments)


# ------------------------------------------------------- market + confidence
def test_high_confidence_market_moves_the_rate(engine, config):
    base = engine.calculate(make_context(), config)
    strong = engine.calculate(
        make_context(market_price_index=1.20, market_confidence="HIGH", market_qualified_count=3),
        config,
    )
    assert strong.recommended_net_rate > base.recommended_net_rate


def test_low_confidence_market_is_shown_but_never_applied(engine, config):
    """The core rule: unusable evidence must not silently move a rate."""
    result = engine.calculate(
        make_context(
            market_price_index=None,
            market_confidence="LOW",
            market_qualified_count=0,
            market_ignored_count=4,
            market_observation_count=4,
        ),
        config,
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.is_ignored is True
    assert market.adjustment_pct == 0.0
    assert market.delta == 0.0
    assert market.label_key == "adjustments.market.ignored_low_confidence"
    assert market.params["gate"] == "MEDIUM"
    assert result.recommended_net_rate == pytest.approx(result.base_net_rate)


def test_ignored_market_stays_a_visible_step(engine, config):
    result = engine.calculate(
        make_context(
            market_price_index=None, market_qualified_count=0,
            market_ignored_count=3, market_observation_count=3,
        ),
        config,
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.is_ignored, "an excluded observation must remain a visible step"
    assert market.label_key == "adjustments.market.ignored_low_confidence"
    assert market.params["ignored_count"] == 3
    assert "market" in result.metadata["ignored_signals"]


def test_missing_market_data_is_neutral_and_recorded_as_missing(engine, config):
    result = engine.calculate(
        make_context(
            market_price_index=None, market_observation_count=0,
            market_qualified_count=0, market_ignored_count=0, missing=("market",),
        ),
        config,
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.adjustment_pct == 0.0 and market.is_neutral
    assert market.label_key == "adjustments.market.unavailable"
    assert "market" in result.metadata["missing_signals"]


def test_market_below_minimum_observations_is_ignored(engine, config):
    config["market"]["min_observations"] = 3
    result = engine.calculate(
        make_context(market_price_index=1.3, market_qualified_count=1), config
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.adjustment_pct == 0.0
    assert market.label_key == "adjustments.market.insufficient"
    assert market.params["qualified_count"] == 1
    assert market.params["min_observations"] == 3


def test_market_adjustment_is_capped(engine, config):
    result = engine.calculate(
        make_context(market_price_index=5.0, market_qualified_count=5), config
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert abs(market.adjustment_pct) <= config["market"]["max_adjustment_pct"] + 1e-9


def test_market_sensitivity_scales_the_adjustment(engine, config):
    config["market"]["sensitivity"] = 0.0
    result = engine.calculate(
        make_context(market_price_index=1.5, market_qualified_count=3), config
    )
    market = next(a for a in result.adjustments if a.code == "market")
    assert market.adjustment_pct == pytest.approx(0.0)


# --------------------------------------------------------------- day of week
def test_day_of_week_is_off_by_default(engine, config):
    assert config["day_of_week"]["enabled"] is False
    assert not any(a.code == "day_of_week" for a in engine.calculate(make_context(), config).adjustments)


def test_day_of_week_applies_when_explicitly_enabled(engine, config):
    config["day_of_week"]["enabled"] = True
    config["day_of_week"]["adjustment_pct"]["saturday"] = 6.0
    result = engine.calculate(make_context(day_of_week="saturday"), config)
    dow = next(a for a in result.adjustments if a.code == "day_of_week")
    assert dow.adjustment_pct == pytest.approx(6.0)


# ------------------------------------------------------------------- bounds
def test_total_dynamic_adjustment_is_bounded(engine, config):
    config["dynamic"]["max_total_adjustment_pct"] = 5.0
    result = engine.calculate(
        make_context(
            pace_gap=0.5, pickup_delta=5.0, is_event=True,
            event_name="Big", event_impact_level="high",
        ),
        config,
    )
    assert result.metadata["bounded_dynamic_pct"] == pytest.approx(5.0)
    assert result.metadata["dynamic_bound_applied"] is True
    assert any(a.code == "dynamic_bound" for a in result.adjustments)


def test_bound_scales_contributions_so_the_breakdown_still_adds_up(engine, config):
    config["dynamic"]["max_total_adjustment_pct"] = 6.0
    result = engine.calculate(
        make_context(pace_gap=0.5, pickup_delta=5.0, is_event=True,
                     event_name="Big", event_impact_level="high"),
        config,
    )
    applied = sum(
        a.adjustment_pct for a in result.adjustments if a.code in ("pace", "recent_pickup", "event", "market")
    )
    assert applied == pytest.approx(6.0, abs=0.01)


def test_negative_total_is_bounded_too(engine, config):
    config["dynamic"]["min_total_adjustment_pct"] = -5.0
    result = engine.calculate(make_context(pace_gap=-0.5, pickup_delta=-5.0), config)
    assert result.metadata["bounded_dynamic_pct"] == pytest.approx(-5.0)


# -------------------------------------------------------------------- clamps
def test_minimum_band_rate_is_enforced(engine, config):
    """Never price below the validated seasonal floor."""
    config["dynamic"]["min_total_adjustment_pct"] = -90.0
    config["pace"]["bands"][0]["adjustment_pct"] = -80.0
    result = engine.calculate(make_context(pace_gap=-0.9), config)
    assert result.recommended_net_rate == pytest.approx(1_800_000)  # low_2 2BR Regular MIN
    assert result.metadata["clamp_applied"] == "min"
    assert any(a.code == "band_min_clamp" for a in result.adjustments)


def test_maximum_band_rate_is_enforced(engine, config):
    config["dynamic"]["max_total_adjustment_pct"] = 90.0
    config["pace"]["bands"][-1]["adjustment_pct"] = 80.0
    result = engine.calculate(make_context(pace_gap=0.9), config)
    assert result.recommended_net_rate == pytest.approx(2_300_000)  # low_2 2BR Regular MAX
    assert result.metadata["clamp_applied"] == "max"
    assert any(a.code == "band_max_clamp" for a in result.adjustments)


def test_clamp_step_names_the_validated_bound(engine, config):
    config["dynamic"]["min_total_adjustment_pct"] = -90.0
    config["pace"]["bands"][0]["adjustment_pct"] = -80.0
    result = engine.calculate(make_context(pace_gap=-0.9), config)
    clamp = next(a for a in result.adjustments if a.code == "band_min_clamp")
    assert clamp.label_key == "adjustments.band_min_clamp"
    assert clamp.params["bound_net_rate"] == pytest.approx(1_800_000)


# ------------------------------------------------------------------ rounding
@pytest.mark.parametrize(
    "value,increment,mode,expected",
    [
        (2_134_567, 10_000, "nearest", 2_130_000),
        (2_135_001, 10_000, "nearest", 2_140_000),
        (2_134_567, 10_000, "up", 2_140_000),
        (2_134_567, 10_000, "down", 2_130_000),
        (2_134_567, 0, "nearest", 2_134_567),
    ],
)
def test_round_rate(value, increment, mode, expected):
    assert _round_rate(value, increment, mode) == pytest.approx(expected)


def test_recommended_rate_lands_on_the_rounding_increment(engine, config):
    config["rounding"]["increment"] = 50_000
    result = engine.calculate(make_context(pace_gap=0.13, pickup_delta=1.2), config)
    assert result.recommended_net_rate % 50_000 == pytest.approx(0, abs=1e-6)


def test_rounding_never_breaks_the_band_floor(engine, config):
    config["rounding"]["increment"] = 200_000
    config["dynamic"]["min_total_adjustment_pct"] = -90.0
    config["pace"]["bands"][0]["adjustment_pct"] = -80.0
    result = engine.calculate(make_context(pace_gap=-0.9), config)
    assert result.recommended_net_rate >= 1_800_000


def test_rounding_never_breaks_the_band_ceiling(engine, config):
    config["rounding"]["increment"] = 200_000
    config["dynamic"]["max_total_adjustment_pct"] = 90.0
    config["pace"]["bands"][-1]["adjustment_pct"] = 80.0
    result = engine.calculate(make_context(pace_gap=0.9), config)
    assert result.recommended_net_rate <= 2_300_000


# --------------------------------------------------------------- breakdown
def test_breakdown_is_arithmetically_consistent(engine, config):
    result = engine.calculate(
        make_context(pace_gap=0.3, pickup_delta=2.5, is_event=True,
                     event_name="Gala", event_impact_level="medium"),
        config,
    )
    running = result.base_net_rate
    for adj in result.adjustments:
        assert adj.price_before == pytest.approx(running, abs=0.02)
        running = adj.price_after
    assert result.recommended_net_rate == pytest.approx(running, abs=0.02)


def test_the_breakdown_identifies_the_season_band_and_each_signal(engine, config):
    result = engine.calculate(
        make_context(pace_gap=0.3, is_event=True, event_name="Marathon",
                     event_impact_level="high"),
        config,
    )
    by_code = {a.code: a for a in result.adjustments}
    assert by_code["rate_band"].params["season_key"] == "low_2"
    assert by_code["rate_band"].params["base_net_rate"] == pytest.approx(2_100_000)
    assert by_code["event"].params["event_name"] == "Marathon"
    assert by_code["pace"].label_key == "adjustments.pace.well_ahead"


def test_change_is_measured_against_the_current_net_rate(engine, config):
    result = engine.calculate(make_context(current_net_rate=1_900_000), config)
    expected = (result.recommended_net_rate - 1_900_000) / 1_900_000 * 100
    assert result.change_pct == pytest.approx(expected, abs=0.01)


def test_metadata_separates_validated_from_unvalidated(engine, config):
    meta = engine.calculate(make_context(), config).metadata
    assert meta["rate_band_status"] == "CLIENT_VALIDATED"
    assert meta["dynamic_assumptions_status"] == "UNVALIDATED"
    assert meta["rate_basis"] == "NET"
    assert meta["mode"] == "shadow"


def test_all_signals_missing_still_returns_the_validated_base(engine, config):
    result = engine.calculate(
        make_context(
            occupancy=None, pace_gap=None, expected_occupancy=None,
            recent_pickup=None, pickup_delta=None, market_price_index=None,
            market_observation_count=0, market_qualified_count=0,
            missing=("occupancy", "pace_gap", "recent_pickup", "market"),
        ),
        config,
    )
    assert result.recommended_net_rate == pytest.approx(2_100_000)


# ------------------------------------------------------------ configuration
def test_changing_a_pace_threshold_changes_the_rate(engine, config):
    before = engine.calculate(make_context(pace_gap=0.3), config)
    config["pace"]["bands"][-1]["adjustment_pct"] = 14.0
    after = engine.calculate(make_context(pace_gap=0.3), config)
    assert after.recommended_net_rate > before.recommended_net_rate


def test_disabling_a_signal_removes_it_from_the_breakdown(engine, config):
    config["pace"]["enabled"] = False
    codes = {a.code for a in engine.calculate(make_context(pace_gap=0.4), config).adjustments}
    assert "pace" not in codes


def test_partial_config_is_merged_with_defaults(engine):
    from dynamic_pricing.pricing import merge_config

    merged = merge_config({"event": {"impact_adjustment_pct": {"high": 25.0}}})
    assert merged["event"]["impact_adjustment_pct"]["high"] == 25.0
    assert merged["pace"]["enabled"] is True  # default preserved
    assert engine.calculate(make_context(), merged).recommended_net_rate > 0
