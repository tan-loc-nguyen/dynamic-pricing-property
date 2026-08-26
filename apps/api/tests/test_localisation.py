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
import re
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


# ---------------------------------------------------------------------------
# Both-directions checks over the message files.
#
# test_every_emittable_key_has_a_translation proves a key EXISTS. Neither of
# these was covered: whether the sentence behind it can actually be filled in,
# and whether anything renders it. A key can be present, perfectly translated,
# and still show English or a raw code to the operator.
# ---------------------------------------------------------------------------

# The frontend enriches a few params before handing them to ICU: a code is
# swapped for the translated word from `vocab`. Mirrored from
# apps/web/lib/adjustments.ts -- if that mapping changes, this must too.
ENRICHED_PARAMS = {"season_key": "season"}

WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
def _placeholders(message: str) -> set[str]:
    """Top-level ICU argument names only.

    A naive regex also matches the BRANCH BODIES of a select
    (`{direction, select, above {above} other {below}}` looks like it needs an
    argument called `above`), so this tracks brace depth and reads a name only
    where an argument can actually appear.
    """
    names: set[str] = set()
    depth = 0
    i = 0
    while i < len(message):
        char = message[i]
        if char == "{":
            if depth == 0:
                j = i + 1
                while j < len(message) and (message[j].isalnum() or message[j] == "_"):
                    j += 1
                name = message[i + 1 : j].strip()
                if name:
                    names.add(name)
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return names

# One scenario per emittable key. A new key with no scenario fails the coverage
# assertion below, so this cannot silently fall behind the engine.
def _scenarios(config):
    wide = copy.deepcopy(config)
    wide["dynamic"]["min_total_adjustment_pct"] = -90.0
    wide["dynamic"]["max_total_adjustment_pct"] = 90.0
    floor_cfg = copy.deepcopy(wide)
    floor_cfg["pace"]["bands"][0]["adjustment_pct"] = -80.0
    ceil_cfg = copy.deepcopy(wide)
    ceil_cfg["pace"]["bands"][-1]["adjustment_pct"] = 80.0
    dow = copy.deepcopy(config)
    dow["day_of_week"] = {"enabled": True, "adjustment_pct": {"thursday": 2.0}}
    few = copy.deepcopy(config)
    few["market"]["min_observations"] = 3
    # An empty band list is the only way _band_for returns None, and it is what
    # the *.no_band messages exist for.
    no_pace_band = copy.deepcopy(config)
    no_pace_band["pace"]["bands"] = []
    no_pickup_band = copy.deepcopy(config)
    no_pickup_band["recent_pickup"]["bands"] = []

    return [
        (config, {}),
        (config, {"band_min_net_rate": None, "band_base_net_rate": None,
                  "band_max_net_rate": None, "season_key": None, "season_label": None,
                  "rate_band_source": "FALLBACK", "current_net_rate": 2_000_000.0}),
        (config, {"pace_gap": -0.25}),
        (config, {"pace_gap": -0.10}),
        (config, {"pace_gap": 0.10}),
        (config, {"pace_gap": 0.30}),
        (config, {"pace_gap": None, "expected_occupancy": None}),
        (config, {"pace_gap": None}),
        (config, {"pickup_delta": -1.5}),
        (config, {"pickup_delta": -0.5}),
        (config, {"pickup_delta": 1.0}),
        (config, {"pickup_delta": 3.0}),
        (config, {"pickup_delta": None}),
        (config, {"is_event": True, "event_name": "X", "event_impact_level": "high"}),
        (config, {"is_event": True, "event_name": "X", "event_adjustment_pct": 5.0}),
        (config, {"market_price_index": 1.2}),
        (config, {"market_qualified_count": 0, "market_ignored_count": 3,
                  "market_price_index": None}),
        (config, {"market_price_index": None, "market_qualified_count": 0}),
        (few, {"market_price_index": 1.2, "market_qualified_count": 1}),
        (dow, {}),
        (no_pace_band, {"pace_gap": -0.25}),
        (no_pickup_band, {"pickup_delta": -1.5}),
        (floor_cfg, {"pace_gap": -0.9}),
        (ceil_cfg, {"pace_gap": 0.9}),
        (config, {"pace_gap": 0.5, "pickup_delta": 5.0, "is_event": True,
                  "event_name": "X", "event_impact_level": "high"}),
    ]


def _numeric_placeholders(message: str) -> set[str]:
    """Argument names the message formats with `, number`."""
    return {
        name
        for name in _placeholders(message)
        if re.search(rf"\{{\s*{re.escape(name)}\s*,\s*number", message)
    }


def _emitted_params(engine, config):
    """Every (label_key, available param names) the engine can actually produce.

    Deliberately a LIST, not a union per key. Unioning hides the failure this
    exists to catch: `rate_band` supplies `season` on almost every row and NOT
    on the no-band fallback row, and a union would report it as supplied.
    """
    emitted: list[tuple[str, set[str], str]] = []
    for index, (cfg, overrides) in enumerate(_scenarios(config)):
        for adj in engine.calculate(make_context(**overrides), copy.deepcopy(cfg)).adjustments:
            if not adj.label_key:
                continue
            names = set(adj.params)
            for code, enriched in ENRICHED_PARAMS.items():
                # The frontend only enriches when the value is a STRING
                # (`typeof x === "string"`), so a null code supplies nothing --
                # which is exactly how {season} came to be unfillable.
                if isinstance(adj.params.get(code), str):
                    names.add(enriched)
            emitted.append((adj.label_key, names, f"scenario #{index}"))
    return emitted


def test_the_scenarios_below_reach_every_emittable_key(engine, config):
    """Guards the guard: an unreached key is an unchecked sentence."""
    reached = {key for key, _, _ in _emitted_params(engine, config)}
    missing = set(EMITTABLE_MESSAGE_KEYS) - reached
    assert not missing, f"no scenario produces: {sorted(missing)}"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_placeholder_in_a_message_is_supplied_by_the_engine(engine, config, locale):
    """A sentence whose placeholder is never filled does not degrade -- ICU
    refuses the whole message, so the operator gets a raw key where the
    explanation should be. This is the same both-directions lesson as
    NUMERIC_LEAVES: existence was checked, satisfiability was not."""
    flat = _flatten(_messages(locale))
    emitted = _emitted_params(engine, config)
    problems: list[str] = []

    for key, params, where in emitted:
        for part in ("label", "reason"):
            message = flat.get(f"{key}.{part}")
            if message is None:
                continue
            for name in _placeholders(message):
                if name not in params:
                    problems.append(
                        f"{locale}: {key}.{part} needs {{{name}}} but the engine does not "
                        f"supply it on {where} (has {sorted(params)})"
                    )
    assert not problems, "\n".join(problems)


def _translation_references() -> tuple[set[str], set[str]]:
    """Every message path the frontend can ask for.

    Each translation function is bound to the namespace it was created with --
    a file commonly has `const t = useTranslations("drawer")` next to
    `const tv = useTranslations("vocab")`, and treating every call as reachable
    from every namespace turns this check into noise.

    Three call shapes are recognised:
      * ``t("a.b")``                -> the exact path
      * ``t(`a.${code}`)``          -> a static PREFIX; anything under it counts
      * ``t(name)`` / ``t(x[y])``   -> fully dynamic, so the whole namespace counts
    """
    exact: set[str] = set()
    prefixes: set[str] = set()
    # Recursive on purpose: `components/*.tsx` missed everything in a
    # subdirectory, so moving a component into components/calendar/ silently
    # dropped it out of this guard and its keys looked dead.
    for path in list(WEB.glob("app/**/*.tsx")) + list(WEB.glob("components/**/*.tsx")) + list(
        WEB.glob("lib/**/*.ts")
    ):
        src = path.read_text(encoding="utf-8")
        bindings = dict(
            re.findall(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*useTranslations\(\s*\"?([^\")]*)\"?\s*\)", src)
        )
        bindings.update(
            dict.fromkeys(
                re.findall(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*await getTranslations\(", src),
                "",
            )
        )
        for var, ns in re.findall(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*await getTranslations\(\{[^}]*namespace:\s*\"([^\"]*)\"", src):
            bindings[var] = ns

        for var, ns in bindings.items():
            for quote in ('"', "'", "`"):
                for arg in re.findall(
                    rf"\b{re.escape(var)}(?:\.rich)?\(\s*{quote}([^{quote}]*?){quote}", src
                ):
                    if "${" in arg:
                        static = arg.split("${")[0]
                        prefixes.add(f"{ns}.{static}".rstrip(".") if ns else static.rstrip("."))
                    else:
                        exact.add(f"{ns}.{arg}" if ns else arg)
            if ns and re.search(rf"\b{re.escape(var)}\(\s*[A-Za-z_][A-Za-z0-9_]*[\.\[(]?", src):
                prefixes.add(ns)
    return exact, prefixes


def test_every_translated_string_is_rendered_somewhere():
    """A key nobody renders is a place the UI is showing English or a raw code.

    Every dead translation found so far had exactly that symptom: the
    Vietnamese existed, and the operator saw `holiday` or `dynamic layer`.
    """
    exact, prefixes = _translation_references()
    dead = []
    for key in _flatten(_messages("en")):
        # adjustments.* are reached through a fully dynamic `${adj.label_key}`
        # and are already checked, in both directions, by
        # test_every_emittable_key_has_a_translation.
        if key.startswith("adjustments."):
            continue
        if key in exact:
            continue
        if any(key.startswith(p + ".") for p in prefixes):
            continue
        dead.append(key)
    assert not dead, (
        f"{len(dead)} translated keys are rendered nowhere — the UI is showing "
        f"English or a raw code in their place: {sorted(dead)}"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_a_number_formatted_placeholder_is_never_given_a_null(engine, config, locale):
    """`{x, number}` cannot be rescued by a fallback the way `{x}` can.

    The enricher swaps a null for an em dash so a bare placeholder still reads,
    but Intl.NumberFormat coerces that dash to NaN — so the operator would see
    "band NaN–NaN" and "NaN%". The guard has to live where the value is
    produced, not where it is formatted.
    """
    flat = _flatten(_messages(locale))
    problems: list[str] = []

    for cfg, overrides in _scenarios(config):
        for adj in engine.calculate(make_context(**overrides), copy.deepcopy(cfg)).adjustments:
            if not adj.label_key:
                continue
            for part in ("label", "reason"):
                message = flat.get(f"{adj.label_key}.{part}")
                if message is None:
                    continue
                for name in _numeric_placeholders(message):
                    if name in adj.params and adj.params[name] is None:
                        problems.append(
                            f"{locale}: {adj.label_key}.{part} formats {{{name}}} as a number "
                            f"but the engine supplied null — it would render NaN"
                        )
    assert not problems, "\n".join(sorted(set(problems)))


def test_every_key_the_frontend_asks_for_exists():
    """The mirror of the check above, and the one that matters at runtime.

    next-intl renders a missing key as the literal path, so `rateBook.roomCategory`
    shipped as a visible column header reading "rateBook.roomCategory" — in BOTH
    languages. A dead key shows English; a missing key shows a dotted path.
    """
    exact, _ = _translation_references()
    flat = _flatten(_messages("en"))
    known = set(flat)
    missing = sorted(
        ref
        for ref in exact
        # A parent path is legitimate: t.rich and namespaced sub-objects.
        if ref and ref not in known and not any(k.startswith(ref + ".") for k in known)
    )
    assert not missing, f"the frontend asks for keys that do not exist: {missing}"


def test_the_engine_decides_the_pace_chips_colour_not_typescript(engine, config):
    """`paceTone()` hardcoded ±0.08 in TypeScript while the chip's TEXT came
    from the engine's configurable bands. Widen "On pace" to ±0.20 — a
    legitimate retune — and a gap of +0.12 produced a GREEN chip reading
    "On pace". That is D28's root cause in the colour channel: tone is semantic
    here, so it can contradict the label it sits on.

    The band's own adjustment decides it, which also works for a band the
    operator invented — TypeScript has no thresholds for those at all.
    """
    cfg = copy.deepcopy(config)
    for band in cfg["pace"]["bands"]:
        if band["key"] == "on_pace":
            band["max_gap"] = 0.20
        if band["key"] == "ahead":
            band["max_gap"] = 0.30

    meta = engine.calculate(make_context(pace_gap=0.12), cfg).metadata
    assert meta["pace_label_key"] == "adjustments.pace.on_pace"
    assert meta["pace_tone"] == "info", "a 0% band must not be coloured as a gain"

    assert engine.calculate(make_context(pace_gap=-0.25), cfg).metadata["pace_tone"] == "down"
    assert engine.calculate(make_context(pace_gap=0.45), cfg).metadata["pace_tone"] == "up"
    blind = engine.calculate(make_context(pace_gap=None, expected_occupancy=None), cfg)
    assert blind.metadata["pace_tone"] == "neutral"


# ---------------------------------------------------------------------------
# Configuration problems
#
# These were left in English on the grounds that translating them would mean a
# second (Python) i18n toolchain. That was the wrong constraint: the strings are
# already structured -- a field path plus a reason plus a value -- so they can
# be emitted as key + params and rendered from the SAME message files by the
# same toolchain, exactly as the pricing explanation now is. And a validation
# error is what an operator sees when they have already made a mistake and are
# unsure, which is the worst place for a language barrier.
# ---------------------------------------------------------------------------
def test_configuration_problems_are_structured_not_prose():
    from dynamic_pricing.pricing.defaults import preview_config

    _config, problems = preview_config({"market": {"sensitivity": "banana"}})
    assert problems, "a non-numeric sensitivity must be reported"
    problem = problems[0]
    assert problem["code"] == "not_a_number"
    assert problem["path"] == "market.sensitivity"
    assert problem["params"]["value"] == "'banana'"
    assert problem["message"], "an English message stays for logs and 422 bodies"


def test_band_problems_are_structured_too():
    from dynamic_pricing.pricing.defaults import default_config, preview_config

    cfg = copy.deepcopy(default_config())
    cfg["pace"]["bands"][0]["max_gap"] = 0.5   # now above the band after it
    _config, problems = preview_config(cfg)
    codes = {p["code"] for p in problems}
    assert "band_threshold_not_increasing" in codes, codes


@pytest.mark.parametrize("locale", LOCALES)
def test_every_configuration_problem_code_has_a_translation(locale):
    from dynamic_pricing.pricing.defaults import PROBLEM_CODES

    flat = _flatten(_messages(locale))
    missing = [code for code in PROBLEM_CODES if f"validation.{code}" not in flat]
    assert not missing, f"{locale}.json is missing validation messages for: {missing}"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_validation_placeholder_is_supplied(engine, config, locale):
    """Same both-directions check as the adjustments, for the other surface.

    `path` is NOT in `params` — it is a sibling field on the problem — so a
    message referencing `{path}` is only fillable if the renderer merges it in.
    Writing this caught the renderer passing `path: ""` and then spreading
    params over it, which rendered every field path as nothing at all.
    """
    from dynamic_pricing.pricing.defaults import default_config, preview_config

    flat = _flatten(_messages(locale))
    bad_configs = [
        {"market": {"sensitivity": "banana"}},
        {"rounding": {"increment": "x"}},
        {"market": {"min_confidence": "BANANA"}},
        {"booking_curve": {"anchors": [{"day": 0}]}},
        {"dynamic": {"min_total_adjustment_pct": 20.0, "max_total_adjustment_pct": 5.0}},
        {"pace": {"bands": "not-a-list"}},
    ]
    broken_band = copy.deepcopy(default_config())
    broken_band["pace"]["bands"][0]["max_gap"] = 0.5
    bad_configs.append(broken_band)

    problems: list[str] = []
    for payload in bad_configs:
        for problem in preview_config(payload)[1]:
            message = flat.get(f"validation.{problem['code']}")
            assert message, f"{locale}: no message for {problem['code']}"
            # The renderer merges `path` in alongside `params`.
            available = set(problem["params"]) | {"path"}
            for name in _placeholders(message):
                if name not in available:
                    problems.append(
                        f"{locale}: validation.{problem['code']} needs {{{name}}}, "
                        f"problem supplies {sorted(available)}"
                    )
            if "path" in _placeholders(message) and not problem["path"]:
                problems.append(
                    f"{locale}: validation.{problem['code']} renders {{path}} but the "
                    f"problem carries no path"
                )
    assert not problems, "\n".join(sorted(set(problems)))


@pytest.mark.parametrize(
    "source,expects_a_band",
    [
        ("CLIENT_VALIDATED", True),
        # An operator editing a band in the Rate Book is a supported action. The
        # band still exists, its numbers are still the ones shown, and its season
        # is still known -- only its PROVENANCE changed, and {source} already
        # says that. Gating the sentence on "is it validated" made an edited band
        # claim no band covered the date: false three ways over.
        ("OPERATOR_EDITED", True),
        ("FALLBACK", False),
    ],
)
def test_the_rate_band_sentence_asks_whether_a_band_exists(engine, config, source, expects_a_band):
    """`rate_band_source` has THREE values, so a boolean gate has to name all
    three. Two earlier versions of this predicate each had fewer states than the
    field they read: `has_band` asked "are there numbers" (always yes, because
    the feature engine substitutes the room type's fallback rates), and its
    replacement asked "is it validated" (no for an edited band).

    The sentence's actual question is narrower than either: is there a band to
    name at all? Provenance is carried separately by {source}.
    """
    ctx = make_context(
        rate_band_source=source,
        season_key=None if source == "FALLBACK" else "low_2",
        band_min_net_rate=1_500_000.0 if source == "FALLBACK" else 1_800_000.0,
        band_base_net_rate=2_000_000.0 if source == "FALLBACK" else 2_100_000.0,
        band_max_net_rate=4_000_000.0 if source == "FALLBACK" else 2_300_000.0,
    )
    params = next(a for a in engine.calculate(ctx, config).adjustments if a.code == "rate_band").params

    assert params["has_rate_band"] is expects_a_band
    assert params["source"] == source, "provenance travels separately and is always named"



@pytest.mark.parametrize("locale", LOCALES)
def test_no_message_escapes_its_own_placeholder(locale):
    """ICU treats an apostrophe before a brace as an ESCAPE character.

    `'{event_name}' falls on this stay date` therefore rendered the literal text
    `{event_name}` — in the explanation, on every event row. Nothing else caught
    it: the placeholder IS declared and IS supplied, so the both-directions
    check passed while the sentence was broken.

    DO NOT fold this into `make lint`'s ICU compile check. An escaped
    placeholder is VALID ICU — it compiles cleanly, so the compiler reports
    nothing. The two guards look overlapping and are not: the compiler catches
    malformed ICU, this catches well-formed ICU that says the wrong thing.
    Consolidating them would silently reopen this exact bug.
    """
    offenders = [
        f"{key}: {value}"
        for key, value in _flatten(_messages(locale)).items()
        if isinstance(value, str) and "'{" in value
    ]
    assert not offenders, (
        "an apostrophe immediately before a placeholder escapes it, so the "
        f"braces render literally: {offenders}"
    )


# ------------------------------------------------- market confidence prose
def test_confidence_is_reported_as_codes_not_prose():
    """The last composed-prose surface. `confidence_reason` explains why an
    observation may or may not move a rate — which is the operator's whole
    decision on that screen — and it was assembled in English from a variable
    list of gaps, exactly like the pricing explanation used to be.
    """
    from dynamic_pricing.providers.market.base import (
        CONFIDENCE_GAP_CODES,
        CONFIDENCE_REASON_CODES,
        MarketObservationDTO,
        score_confidence,
    )

    complete = MarketObservationDTO(
        stay_date=date(2026, 9, 10), competitor_name="Comp", observed_price=2_000_000.0,
        source="manual", room_category="2br_regular", price_basis="NET",
        tax_inclusion="INCLUSIVE", fee_inclusion="INCLUSIVE", length_of_stay=1,
        promotion_status="NONE",
    )
    confidence, reason_code, gaps = score_confidence(complete)
    assert confidence == "HIGH"
    assert reason_code == "comparable_net" and reason_code in CONFIDENCE_REASON_CODES
    assert gaps == []

    vague = MarketObservationDTO(
        stay_date=date(2026, 9, 10), competitor_name="Comp", observed_price=2_000_000.0,
        source="manual", room_category=None, price_basis="UNKNOWN",
    )
    _confidence, reason_code, gaps = score_confidence(vague)
    assert reason_code == "not_comparable"
    assert "no_room_category" in gaps and "basis_unknown" in gaps
    assert set(gaps) <= set(CONFIDENCE_GAP_CODES)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_confidence_code_has_a_translation(locale):
    from dynamic_pricing.providers.market.base import (
        CONFIDENCE_GAP_CODES,
        CONFIDENCE_REASON_CODES,
    )

    flat = _flatten(_messages(locale))
    missing = [f"confidenceReason.{c}" for c in CONFIDENCE_REASON_CODES
               if f"confidenceReason.{c}" not in flat]
    missing += [f"confidenceGap.{c}" for c in CONFIDENCE_GAP_CODES
                if f"confidenceGap.{c}" not in flat]
    assert not missing, f"{locale}.json is missing: {missing}"


# --------------------------------------------------------------------------
# Runtime enums that cross to the frontend
# --------------------------------------------------------------------------
def test_every_rate_provenance_the_backend_can_emit_has_a_rendering(locale=None):
    """Three green guards missed a blank amber box, because each answered a
    question ADJACENT to the property.

    `seasonal_base` passed the "is it published?" gate, matched no rendering
    branch, and drew a styled div with nothing in it — and it is the provenance
    every UNBOOKED night gets, so it is the most common non-published value and
    the one an operator most needs explained.

    * "every translated string is rendered" passed — it was never translated.
    * "every key the frontend asks for exists" passed — nobody asked.
    * the human-field guard passed — `rate_provenance` has a component reader.

    The property none of them state is "every value the backend can EMIT has a
    rendering". This is `EMITTABLE_MESSAGE_KEYS` in the other direction, for a
    runtime enum instead of a message key.
    """
    from dynamic_pricing.providers.pms.base import RATE_PROVENANCE_VALUES

    for loc in LOCALES:
        flat = _flatten(_messages(loc))
        missing = [
            value
            for value in RATE_PROVENANCE_VALUES
            # "published" is deliberately silent: annotating every ordinary row
            # would be noise. Every OTHER value means the rate was reconstructed
            # and must say so.
            if value != "published" and f"dataSource.provenance.{value}" not in flat
        ]
        assert not missing, (
            f"{loc}: the backend can emit rate_provenance={missing}, and there is no "
            f"string for it. The drawer gates on `!== 'published'`, so an unhandled "
            f"value renders as a styled, EMPTY box."
        )


def test_no_rate_provenance_string_exists_for_a_value_the_backend_cannot_emit():
    """The other direction, same as the numeric-leaf guard: a message for a
    value nothing produces is a claim about behaviour that is not true."""
    from dynamic_pricing.providers.pms.base import RATE_PROVENANCE_VALUES

    flat = _flatten(_messages("en"))
    prefix = "dataSource.provenance."
    declared = {k[len(prefix):] for k in flat if k.startswith(prefix)}
    stale = sorted(declared - set(RATE_PROVENANCE_VALUES))
    assert not stale, f"strings for provenance values the backend never emits: {stale}"


def test_the_clamp_union_lists_exactly_what_the_engine_emits():
    """`clamp_applied` was typed `string | null` while the engine emits only
    "min"/"max", and viz.tsx renders it with a ternary — so a third value would
    have rendered confidently as MAX. A union WIDER than reality is the same
    class as one narrower than it: both stop the compiler helping."""
    import re

    engine = (
        Path(__file__).resolve().parents[1] / "dynamic_pricing" / "pricing" / "engine.py"
    ).read_text(encoding="utf-8")
    emitted = set(re.findall(r'clamp_applied = "([a-z]+)"', engine))
    assert emitted, "the engine no longer assigns clamp_applied as a literal"

    source = (WEB / "lib" / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"clamp_applied: ([^;]+);", source)
    assert match, "clamp_applied is no longer declared in lib/types.ts"
    declared = set(re.findall(r'"([a-z]+)"', match.group(1)))
    assert declared == emitted, (
        f"lib/types.ts declares clamp_applied as {sorted(declared)} but the engine "
        f"emits {sorted(emitted)}"
    )


def test_the_typescript_union_lists_exactly_the_provenance_values_python_emits():
    """The fifth copy of this value set, and the one that bites hardest.

    `tsc` reported the `seasonal_base` branch as an impossible comparison
    because the union omitted the value — which is precisely the bug that
    deleted the drawer's unpriced branch when `Status` omitted `"error"`. A
    union narrower than reality does not fail loudly; it convinces the compiler
    that correct handling is dead code.
    """
    import re

    from dynamic_pricing.providers.pms.base import RATE_PROVENANCE_VALUES

    source = (WEB / "lib" / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"rate_provenance:\s*([^;]+);", source)
    assert match, "rate_provenance is no longer declared in lib/types.ts"
    # Strip // comments first: the explanation beside this union quotes another
    # union's values, and a regex over the raw text reads those as declarations.
    body = "\n".join(
        line.split("//")[0] for line in match.group(1).splitlines()
    )
    declared = set(re.findall(r'"([a-z_]+)"', body))
    assert declared == set(RATE_PROVENANCE_VALUES), (
        f"lib/types.ts declares {sorted(declared)} but the backend emits "
        f"{sorted(RATE_PROVENANCE_VALUES)}"
    )
