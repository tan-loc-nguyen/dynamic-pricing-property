"""The explanation must survive translation.

This product's value is the explanation, and until now the engine composed it
as finished English prose and persisted it. A Vietnamese operator could not
read the one thing they most need to read, and no frontend i18n library could
reach it — it arrives at React as an opaque string.

So the engine stops writing sentences and starts emitting the *ingredients*:
a message key plus the numbers that key interpolates. The sentence is composed
at render time, in whichever language is being viewed.

These tests pin that contract from both ends:
  * the engine emits a key + params for every step it can produce, and
  * every key it can emit has a translation in BOTH locales.

The second half is the important one. Without it a missing Vietnamese string
is a blank line discovered in front of a client; with it, it is a test failure.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from conftest import make_context
from dynamic_pricing.pricing.engine import EMITTABLE_MESSAGE_KEYS

MESSAGES_DIR = Path(__file__).resolve().parents[3] / "apps" / "web" / "messages"
LOCALES = ("en", "vi")


def _messages(locale: str) -> dict:
    return json.loads((MESSAGES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _flatten(node, trail: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{trail}.{key}" if trail else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


# --------------------------------------------------------------- the contract
def test_every_adjustment_carries_a_message_key_instead_of_prose(engine, config):
    """No adjustment may ship a pre-composed English sentence."""
    result = engine.calculate(make_context(), config)
    assert result.adjustments, "expected a breakdown to inspect"
    for adj in result.adjustments:
        assert adj.label_key, f"{adj.code} has no message key"
        assert isinstance(adj.params, dict), f"{adj.code} has no params dict"
        assert not hasattr(adj, "reason"), (
            f"{adj.code} still carries prose; the sentence belongs in the message file"
        )


def test_the_engine_no_longer_composes_an_explanation(engine, config):
    """The paragraph was a restatement of the breakdown beside it."""
    result = engine.calculate(make_context(), config)
    assert not hasattr(result, "explanation")


def test_pace_params_carry_the_numbers_the_sentence_needs(engine, config):
    """The Vietnamese sentence needs the same figures the English one used."""
    ctx = make_context(occupancy=0.20, expected_occupancy=0.45, pace_gap=-0.25, days_to_arrival=30)
    pace = next(a for a in engine.calculate(ctx, config).adjustments if a.code == "pace")

    assert pace.label_key == "adjustments.pace.well_behind"
    assert pace.params["occupancy"] == pytest.approx(0.20)
    assert pace.params["expected_occupancy"] == pytest.approx(0.45)
    assert pace.params["days_to_arrival"] == 30
    assert pace.params["gap_pp"] == pytest.approx(25, abs=0.5)


def test_rate_band_params_carry_the_band_and_its_provenance(engine, config):
    band = next(a for a in engine.calculate(make_context(), config).adjustments if a.code == "rate_band")
    assert band.label_key == "adjustments.rate_band"
    assert band.params["base_net_rate"] == pytest.approx(2_100_000)
    assert band.params["min_net_rate"] == pytest.approx(1_800_000)
    assert band.params["max_net_rate"] == pytest.approx(2_300_000)
    assert band.params["source"] == "CLIENT_VALIDATED"
    assert band.params["rate_basis"] == "NET"


def test_clamp_params_name_the_validated_bound(engine, config):
    """The floor sentence must be able to quote the floor in either language."""
    config["dynamic"]["min_total_adjustment_pct"] = -90.0
    config["pace"]["bands"][0]["adjustment_pct"] = -80.0
    result = engine.calculate(make_context(pace_gap=-0.9), config)
    clamp = next(a for a in result.adjustments if a.code == "band_min_clamp")
    assert clamp.label_key == "adjustments.band_min_clamp"
    assert clamp.params["bound_net_rate"] == pytest.approx(1_800_000)


def test_ignored_market_is_still_an_explicit_step(engine, config):
    """Low-confidence evidence stays visible — as a key, not a sentence."""
    ctx = make_context(market_qualified_count=0, market_ignored_count=4, market_price_index=None)
    market = next(a for a in engine.calculate(ctx, config).adjustments if a.code == "market")
    assert market.is_ignored
    assert market.label_key == "adjustments.market.ignored_low_confidence"
    assert market.params["ignored_count"] == 4
    assert market.params["gate"] == "MEDIUM"


# ------------------------------------------------- operator-authored bands
def test_an_operator_authored_band_falls_back_to_its_own_label(engine, config):
    """A renamed or invented band has no shipped translation, and must not be
    silently dropped or mistranslated into an unrelated band's wording."""
    cfg = copy.deepcopy(config)
    cfg["pace"]["bands"] = [
        {"label": "Chậm nghiêm trọng", "max_gap": 99.0, "adjustment_pct": -6.0},
    ]
    ctx = make_context(pace_gap=-0.30)
    pace = next(a for a in engine.calculate(ctx, cfg).adjustments if a.code == "pace")

    assert pace.label_key is None, "an operator's own wording has no message key"
    assert pace.label == "Chậm nghiêm trọng"


# ------------------------------------------------------- translation coverage
def test_every_key_the_engine_can_emit_is_declared(engine, config):
    """EMITTABLE_MESSAGE_KEYS is the contract the locale files are checked against,
    so it must not drift from what the engine actually produces."""
    produced = {
        a.label_key for a in engine.calculate(make_context(), config).adjustments if a.label_key
    }
    undeclared = produced - set(EMITTABLE_MESSAGE_KEYS)
    assert not undeclared, f"engine emits keys that are not declared: {sorted(undeclared)}"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_emittable_key_has_a_translation(locale):
    """A missing Vietnamese string must be a test failure, not a blank line
    discovered during a client demo."""
    flat = _flatten(_messages(locale))
    missing = [
        key
        for key in EMITTABLE_MESSAGE_KEYS
        if f"{key}.label" not in flat or f"{key}.reason" not in flat
    ]
    assert not missing, f"{locale}.json is missing label/reason for: {missing}"


def test_the_locales_describe_exactly_the_same_things():
    """Divergent key sets are how one language quietly loses a feature."""
    en, vi = _flatten(_messages("en")), _flatten(_messages("vi"))
    assert set(en) == set(vi), (
        f"only in en: {sorted(set(en) - set(vi))}; only in vi: {sorted(set(vi) - set(en))}"
    )


def test_vietnamese_is_actually_translated():
    """A copy of the English file would pass every structural check above."""
    en, vi = _flatten(_messages("en")), _flatten(_messages("vi"))
    shared = [k for k in en if en[k] and en[k] == vi.get(k)]
    # Placeholders-only strings ("{pct}") legitimately match across locales.
    suspicious = [k for k in shared if any(c.isalpha() for c in en[k].replace("{", " {"))]
    identical_share = len(suspicious) / max(len(en), 1)
    assert identical_share < 0.25, (
        f"{identical_share:.0%} of Vietnamese strings are identical to the English — "
        f"untranslated: {sorted(suspicious)[:10]}"
    )


# ------------------------------------------------------------- band keys
@pytest.mark.parametrize("section,expected", [
    ("pace", {"well_behind", "behind", "on_pace", "ahead", "well_ahead"}),
    ("recent_pickup", {"stalled", "slowing", "as_expected", "accelerating", "surging"}),
])
def test_shipped_bands_carry_stable_keys(config, section, expected):
    """The band's key is what survives a rename; the label is not."""
    keys = {b.get("key") for b in config[section]["bands"]}
    assert keys == expected


def test_a_shipped_band_key_survives_the_operator_renaming_its_label(engine, config):
    cfg = copy.deepcopy(config)
    for band in cfg["pace"]["bands"]:
        band["label"] = f"renamed {band['key']}"
    ctx = make_context(pace_gap=-0.30)
    pace = next(a for a in engine.calculate(ctx, cfg).adjustments if a.code == "pace")
    assert pace.label_key == "adjustments.pace.well_behind"


# ------------------------------------------------- what replaced the paragraph
def test_the_realised_and_signalled_percentages_stay_distinguishable(engine, config):
    """Regression guard for the deletion, not a driver of it.

    This passes before the refactor and must keep passing after. The deleted
    explanation reconciled 'signals wanted X, the rate is Y'; that
    reconciliation has to survive as data, or clamped rows go back to
    contradicting the table beside them (the bug fixed in 21f5845)."""
    config["dynamic"]["min_total_adjustment_pct"] = -90.0
    config["pace"]["bands"][0]["adjustment_pct"] = -80.0
    result = engine.calculate(make_context(pace_gap=-0.9), config)

    assert result.metadata["clamp_applied"] == "min"
    assert result.metadata["bounded_dynamic_pct"] < result.total_adjustment_pct, (
        "a floor-clamped row realises LESS of a discount than its signals asked for"
    )


# ------------------------------------------------------------- date handling
def test_stay_dates_are_emitted_as_iso_not_formatted_prose(engine, config):
    """'Mon 24 Aug' cannot be re-rendered in Vietnamese; an ISO date can."""
    ctx = make_context(stay_date=date(2026, 9, 10))
    band = next(a for a in engine.calculate(ctx, config).adjustments if a.code == "rate_band")
    assert band.params.get("stay_date") == "2026-09-10"


# ------------------------------------- the table must not re-derive the band
def test_metadata_carries_the_band_keys_the_table_needs(engine, config):
    """The list endpoint renders a pace/pickup label per row but never loads the
    adjustments. Without the engine's own key there, TypeScript has to re-derive
    the band from thresholds — which is exactly how the table came to say
    'On pace' beside a drawer showing '+4% Ahead of pace' (D28)."""
    ctx = make_context(pace_gap=-0.25, pickup_delta=-1.5)
    meta = engine.calculate(ctx, config).metadata

    assert meta["pace_label_key"] == "adjustments.pace.well_behind"
    assert meta["pickup_label_key"] == "adjustments.recent_pickup.stalled"


def test_band_keys_are_absent_rather_than_wrong_when_a_signal_is_blind(engine, config):
    ctx = make_context(pace_gap=None, expected_occupancy=None, pickup_delta=None)
    meta = engine.calculate(ctx, config).metadata
    assert meta["pace_label_key"] == "adjustments.pace.unavailable"
    assert meta["pickup_label_key"] == "adjustments.recent_pickup.unavailable"


def test_an_operator_renamed_band_still_labels_the_table_row(engine, config):
    """The table has no adjustments to read, only the metadata keys — so if the
    metadata carries a key but not the operator's own wording, a renamed band
    renders as the label in the drawer and as "no data" in the row beside it.

    That is precisely the D28 contradiction this change was supposed to remove,
    reintroduced one level down.
    """
    cfg = copy.deepcopy(config)
    cfg["pace"]["bands"] = [{"label": "Chậm nghiêm trọng", "max_gap": 99.0, "adjustment_pct": -6.0}]
    meta = engine.calculate(make_context(pace_gap=-0.30), cfg).metadata

    assert meta["pace_label_key"] is None
    assert meta["pace_label"] == "Chậm nghiêm trọng", (
        "the row must be able to show what the drawer shows"
    )
