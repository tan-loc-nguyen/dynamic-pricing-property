"""EXPERIMENTAL dynamic strategy configuration.

=============================================================================
 EVERYTHING IN THIS FILE IS UNVALIDATED.

 The client-validated MIN/BASE/MAX rate table lives in ``rate_book.py`` and is
 deliberately NOT here — validated fact and unvalidated experiment must never
 be mixed in one config blob. This file holds only the *dynamic layer* the
 client asked for on top of their rate table: pace, pickup, events, market.

 Each entry maps to an ID in ASSUMPTIONS.md (U1, U2, ...) for operator review.
=============================================================================

Design rules for this layer:
  * Adjustments are ADDITIVE percentages of the band BASE rate, not stacked
    multipliers — bounded and easy to reason about.
  * Signals must not double-count the same demand condition. Pace position and
    recent pickup measure different things (level vs. acceleration).
  * Seasonality is NOT here: the rate band already encodes it.
"""

from __future__ import annotations

import copy
from typing import Any

CONFIG_SCHEMA_VERSION = 2

DEMO_DEFAULTS: dict[str, Any] = {
    "schema_version": CONFIG_SCHEMA_VERSION,
    "label": "demo-defaults",
    "currency": "VND",
    # Shadow mode: recommend, never push. The default and only supported mode.
    "mode": "shadow",

    # ------------------------------------------------------------------ U10
    "rounding": {
        "increment": 10_000,
        "mode": "nearest",
    },

    # ---------------------------------------------------------------- U8
    # Hard bound on the whole dynamic layer, applied BEFORE the band clamp.
    "dynamic": {
        "max_total_adjustment_pct": 15.0,
        "min_total_adjustment_pct": -15.0,
    },

    # ---------------------------------------------------------------- U2
    # Pace position: on-the-books occupancy vs the booking curve's expectation.
    # This is the PRIMARY demand signal. Bands are on pace_gap (fraction:
    # 0.10 = 10 percentage points ahead of expectation).
    # ``key`` is the stable identity of a SHIPPED band -- it is what the message
    # files translate. ``label`` is the operator-facing English wording and can
    # be renamed freely; a band an operator invents has no key, and its own
    # wording is shown verbatim rather than mistranslated.
    "pace": {
        "enabled": True,
        "bands": [
            {"key": "well_behind", "label": "Well behind pace", "max_gap": -0.20, "adjustment_pct": -8.0},
            {"key": "behind", "label": "Behind pace", "max_gap": -0.08, "adjustment_pct": -4.0},
            {"key": "on_pace", "label": "On pace", "max_gap": 0.08, "adjustment_pct": 0.0},
            {"key": "ahead", "label": "Ahead of pace", "max_gap": 0.20, "adjustment_pct": 4.0},
            {"key": "well_ahead", "label": "Well ahead of pace", "max_gap": 99.0, "adjustment_pct": 8.0},
        ],
    },

    # ---------------------------------------------------------------- U3
    # Recent pickup: booking ACCELERATION over the last window. Distinct from
    # pace position, which is a level. Kept small so it cannot dominate.
    "recent_pickup": {
        "enabled": True,
        "lookback_days": 7,
        "expected_pickup_per_week": 1.0,
        "bands": [
            {"key": "stalled", "label": "Pickup stalled", "max_delta": -1.0, "adjustment_pct": -3.0},
            {"key": "slowing", "label": "Pickup slowing", "max_delta": -0.25, "adjustment_pct": -1.5},
            {"key": "as_expected", "label": "Pickup as expected", "max_delta": 0.5, "adjustment_pct": 0.0},
            {"key": "accelerating", "label": "Pickup accelerating", "max_delta": 2.0, "adjustment_pct": 2.0},
            {"key": "surging", "label": "Pickup surging", "max_delta": 999.0, "adjustment_pct": 4.0},
        ],
    },

    # ---------------------------------------------------------------- U4
    "event": {
        "enabled": True,
        "impact_adjustment_pct": {
            "low": 3.0,
            "medium": 8.0,
            "high": 15.0,
        },
    },

    # ---------------------------------------------------------------- U5, U6
    "market": {
        "enabled": True,
        # Only observations at or above this confidence can move a price.
        # HIGH | MEDIUM | LOW  — LOW effectively disables the gate.
        "min_confidence": "MEDIUM",
        "min_observations": 2,
        "observation_max_age_days": 14,
        # adjustment_pct = sensitivity * (market_index - 1) * 100, then capped.
        "sensitivity": 0.50,
        "max_adjustment_pct": 5.0,
    },

    # ---------------------------------------------------------------- U7
    # OFF by default: the client has not confirmed any weekday pattern, and
    # the seasonal table shows no day-of-week structure at all.
    "day_of_week": {
        "enabled": False,
        "adjustment_pct": {
            "monday": 0.0,
            "tuesday": 0.0,
            "wednesday": 0.0,
            "thursday": 0.0,
            "friday": 0.0,
            "saturday": 0.0,
            "sunday": 0.0,
        },
    },

    # ---------------------------------------------------------------- U1
    # Booking curve shape. See features/booking_curve.py — UNVALIDATED.
    "booking_curve": {
        "provider": "demo",
        "anchors": None,        # null = module defaults
        "season_pace": None,
        "category_pace": None,
    },

}

# Ordered metadata for the Settings UI. Every entry here is EXPERIMENTAL —
# the validated rate book is served separately.
EXPERIMENTAL_SECTIONS = [
    "pace",
    "recent_pickup",
    "event",
    "market",
    "day_of_week",
    "dynamic",
    "rounding",
    "booking_curve",
]


def default_config() -> dict[str, Any]:
    """Deep copy so callers can never mutate the module-level default."""
    return copy.deepcopy(DEMO_DEFAULTS)


def merge_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge a partial payload over the demo defaults.

    Guarantees the engine always receives a fully-populated config, so a
    partially-filled Settings form can never crash a pricing run.
    """
    base = default_config()
    if not payload:
        return base
    return _deep_merge(base, payload)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        elif value is None and base.get(key) is not None:
            # A cleared field in the Settings UI arrives as null. Treat that as
            # "fall back to the default", never as "set this to None" -- a null
            # reaching the engine would raise inside float() and silently skip
            # every row of the pricing run.
            # Keys whose default is already None (e.g. booking_curve.anchors)
            # keep their intended nullability, because base.get(key) is None.
            continue
        else:
            base[key] = value
    return base



class ConfigurationInvalid(ValueError):
    """A configuration that would price incorrectly if saved."""


# ---------------------------------------------------------------------------
# Boundary coercion
#
# Every numeric leaf the engine or feature layer will later cast, declared once.
# The config SHAPE stays free-form -- unknown keys pass through untouched, so
# the payload can still evolve after operator interviews without a migration.
# Only the leaves that get cast are checked, and they are checked HERE rather
# than at the point of cast, because those casts happen in three different
# places with three different error-handling stories:
#   * inside the per-row loop      -> repetition guard catches it
#   * in FeatureEngine.__init__    -> outside the loop, nothing catches it
#   * inside validate_config       -> the validator crashes on its own input
# Coercing once at the boundary means none of those has to care.
#
# Path syntax:  "a.b"  a dict key      "a.*"  every value of a dict
#               "a[].b"  every member of a list
# ---------------------------------------------------------------------------
NUMERIC_LEAVES: list[tuple[str, type]] = [
    ("rounding.increment", int),
    ("dynamic.max_total_adjustment_pct", float),
    ("dynamic.min_total_adjustment_pct", float),
    ("pace.bands[].max_gap", float),
    ("pace.bands[].adjustment_pct", float),
    ("recent_pickup.lookback_days", int),
    ("recent_pickup.expected_pickup_per_week", float),
    ("recent_pickup.bands[].max_delta", float),
    ("recent_pickup.bands[].adjustment_pct", float),
    ("event.impact_adjustment_pct.*", float),
    ("market.sensitivity", float),
    ("market.max_adjustment_pct", float),
    ("market.min_observations", int),
    ("market.observation_max_age_days", int),
    ("day_of_week.adjustment_pct.*", float),
    ("booking_curve.anchors[].days", int),
    ("booking_curve.anchors[].expected", float),
]

# Numeric leaves that are genuinely never cast, so need no coercion. Anything
# NOT here and NOT matched by NUMERIC_LEAVES fails the coverage test.
UNCOERCED_NUMERIC_LEAVES = {"schema_version"}

# String fields with a closed set of valid values. Unvalidated, these fail
# silently: an unknown confidence level was treated as MEDIUM and rendered
# straight into operator-facing copy ("below the BANANA confidence bar").
ENUM_LEAVES: list[tuple[str, tuple[str, ...]]] = [
    ("rounding.mode", ("nearest", "up", "down")),
    ("market.min_confidence", ("HIGH", "MEDIUM", "LOW", "UNUSABLE")),
    ("booking_curve.provider", ("demo", "historical")),
    ("mode", ("shadow",)),
]


def _walk(node: Any, parts: list[str], trail: str = ""):
    """Yield (container, key, path) for every leaf a path expression matches."""
    if not parts:
        return
    head, rest = parts[0], parts[1:]

    if head.endswith("[]"):
        name = head[:-2]
        if not isinstance(node, dict):
            return
        seq = node.get(name)
        if not isinstance(seq, list):
            return
        for i, item in enumerate(seq):
            yield from _walk(item, rest, f"{trail}{name}[{i}].")
        return

    if head == "*":
        if not isinstance(node, dict):
            return
        for key in list(node):
            if rest:
                yield from _walk(node[key], rest, f"{trail}{key}.")
            else:
                yield node, key, f"{trail}{key}"
        return

    if not isinstance(node, dict):
        return
    if rest:
        if head in node:
            yield from _walk(node[head], rest, f"{trail}{head}.")
        return
    if head in node:
        yield node, head, f"{trail}{head}"


def _default_at(path: str, config: dict[str, Any] | None = None) -> Any:
    """The shipped default for a concrete path, used to repair a cleared field.

    List members are matched by their ``label``, NEVER by index. The editor lets
    an operator reorder bands, and index matching then restores a semantically
    unrelated value -- clearing the premium on a reordered 'Well ahead of pace'
    silently filled in 'Well behind pace''s -8% discount, with no problem
    reported. Returns None when the label has no shipped counterpart, so the
    field is reported as required instead of being guessed at.
    """
    node: Any = DEMO_DEFAULTS
    live: Any = config
    for part in path.replace("]", "").split("."):
        if "[" in part:
            name, index = part.split("[")
            shipped = node.get(name) if isinstance(node, dict) else None
            current = live.get(name) if isinstance(live, dict) else None
            if not isinstance(shipped, list) or not isinstance(current, list):
                return None
            idx = int(index)
            if idx >= len(current) or not isinstance(current[idx], dict):
                return None
            label = current[idx].get("label")
            match = next(
                (b for b in shipped if isinstance(b, dict) and b.get("label") == label), None
            )
            if match is None:
                return None  # operator-authored band: no shipped default exists
            node, live = match, current[idx]
        else:
            node = node.get(part) if isinstance(node, dict) else None
            live = live.get(part) if isinstance(live, dict) else None
        if node is None:
            return None
    return node


# List members whose keys are read positionally by name. A MISSING key here is
# invisible to NUMERIC_LEAVES (which only visits keys that exist), so it needs
# stating separately -- this is how {"anchors": [{"day": 0}]} reached a
# KeyError inside FeatureEngine construction.
REQUIRED_LIST_KEYS: list[tuple[str, tuple[str, ...]]] = [
    ("booking_curve.anchors", ("days", "expected")),
    ("pace.bands", ("max_gap", "adjustment_pct")),
    ("recent_pickup.bands", ("max_delta", "adjustment_pct")),
]


def _required_key_problems(config: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for path, required in REQUIRED_LIST_KEYS:
        node: Any = config
        for part in path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            continue  # legitimately absent (e.g. anchors: null -> module defaults)
        if not isinstance(node, list):
            problems.append(f"{path} must be a list.")
            continue
        for i, item in enumerate(node):
            if not isinstance(item, dict):
                problems.append(f"{path}[{i}] must be an object.")
                continue
            for key in required:
                if key not in item:
                    problems.append(f"{path}[{i}] is missing required field '{key}'.")
    return problems


def coerce_config(
    config: dict[str, Any], *, repair: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """Coerce every numeric leaf, reporting the field path on failure.

    A cleared field (None) falls back to the shipped default. This is what makes
    the Settings UI's "clear a field to reset it" behaviour true for band members
    too -- `_deep_merge` cannot do it there, because bands are a LIST and it only
    recurses into dicts.

    ``repair=True`` additionally substitutes the default for a value that CANNOT
    be coerced, so a caller that must not crash (the live preview) still gets a
    usable config. The problem is still reported either way -- repairing without
    reporting would be the silent substitution this codebase keeps removing.
    """
    # Structural problems are reported ALONGSIDE type problems, not instead of
    # them: prepare_config promises the operator every bad field path in one
    # list, and an early return made that promise false.
    problems: list[str] = _required_key_problems(config)

    for expression, kind in NUMERIC_LEAVES:
        for container, key, path in _walk(config, expression.split(".")):
            value = container[key]
            if value is None:
                fallback = _default_at(path, config)
                if fallback is None:
                    problems.append(f"{path} is required and cannot be empty.")
                else:
                    container[key] = fallback
                continue
            if isinstance(value, bool):
                problems.append(f"{path} must be a number, got a boolean.")
                continue
            try:
                coerced = float(value)
            except (TypeError, ValueError):
                problems.append(f"{path} must be a number, got {value!r}.")
                if repair:
                    fallback = _default_at(path, config)
                    if fallback is not None:
                        container[key] = fallback
                continue
            if kind is int:
                # Reject rather than truncate, and say why. Previously 7.5
                # silently became 7 while "7.5" was rejected as "not a number",
                # which is both wrong (7.5 IS a number) and asymmetric.
                if coerced != int(coerced):
                    problems.append(f"{path} must be a whole number, got {value!r}.")
                    if repair:
                        fallback = _default_at(path, config)
                        if fallback is not None:
                            container[key] = fallback
                    continue
                container[key] = int(coerced)
            else:
                container[key] = coerced

    for path, allowed in ENUM_LEAVES:
        for container, key, resolved in _walk(config, path.split(".")):
            value = container[key]
            if value is None:
                fallback = _default_at(resolved, config)
                if fallback is not None:
                    container[key] = fallback
                continue
            if value not in allowed:
                problems.append(
                    f"{resolved} must be one of {', '.join(allowed)}; got {value!r}."
                )
                if repair:
                    fallback = _default_at(resolved, config)
                    if fallback is not None:
                        container[key] = fallback
    return config, problems


def _band_problems(
    bands: list, key: str, label: str, domain_min: float, domain_max: float, inclusive: bool
) -> list[str]:
    """Exact reachability, derived from the SUBMITTED thresholds.

    Deliberately NOT sample-based. Probing with a fixed list of numbers cannot
    prove reachability for operator-chosen thresholds: widening a band to
    [-0.20, -0.10) is perfectly legitimate, but if no sample lands inside it the
    operator is told their band is impossible and blocked from tuning it.
    Comparing consecutive thresholds decides it exactly, for any thresholds.
    """
    problems: list[str] = []
    if not isinstance(bands, list) or not bands:
        return problems

    thresholds: list[float] = []
    for i, band in enumerate(bands):
        if not isinstance(band, dict):
            problems.append(f"{label} band #{i + 1} is not a valid band.")
            return problems
        value = band.get(key)
        if value is None:
            problems.append(f"{label} band '{band.get('label', i + 1)}' needs a {key} threshold.")
            return problems
        thresholds.append(float(value))

    for i, band in enumerate(bands):
        name = band.get("label", f"#{i + 1}")
        upper = thresholds[i]
        lower = domain_min if i == 0 else thresholds[i - 1]
        if i > 0 and thresholds[i] <= thresholds[i - 1]:
            problems.append(
                f"{label} band '{name}' has a threshold ({upper:g}) at or below the band "
                f"before it ({thresholds[i - 1]:g}); thresholds must increase."
            )
            continue
        # The interval this band owns is [lower, upper) -- or [lower, upper]
        # when the comparison is inclusive. Empty interval == unreachable band.
        if lower > domain_max:
            problems.append(f"{label} band '{name}' can never be selected: it starts above the highest possible value.")
        elif (lower >= upper) if not inclusive else (lower > upper):
            problems.append(f"{label} band '{name}' can never be selected: its range is empty.")
    return problems


def validate_config(config: dict[str, Any]) -> list[str]:
    """Logic problems in an ALREADY-COERCED configuration.

    Assumes coerce_config has run, so every numeric leaf is a number and this
    can concern itself with meaning rather than types.
    """
    problems: list[str] = []

    pace = config.get("pace", {})
    if pace.get("enabled", True):
        # pace_gap is actual minus expected occupancy, so it spans [-1, 1].
        problems += _band_problems(pace.get("bands", []), "max_gap", "Pace", -1.0, 1.0, False)

    pickup = config.get("recent_pickup", {})
    if pickup.get("enabled", True):
        expected = float(pickup.get("expected_pickup_per_week", 1.0) or 1.0) * (
            float(pickup.get("lookback_days", 7) or 7) / 7.0
        )
        # recent_pickup cannot be negative, so -expected is the true floor.
        problems += _band_problems(
            pickup.get("bands", []), "max_delta", "Pickup", -expected, float("inf"), True
        )

    dynamic = config.get("dynamic", {})
    lo, hi = dynamic.get("min_total_adjustment_pct"), dynamic.get("max_total_adjustment_pct")
    if lo is not None and hi is not None and float(lo) > float(hi):
        problems.append(f"Minimum total adjustment ({lo}%) exceeds the maximum ({hi}%).")

    return problems


def prepare_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Merge -> coerce -> validate. The single entry point for a saved config.

    Raises ConfigurationInvalid with every field path that is wrong, so the
    operator gets one actionable list rather than one error per save attempt.
    """
    merged = merge_config(payload)
    merged, problems = coerce_config(merged)
    if problems:
        # Stop here. validate_config assumes coerced input, so running it on a
        # config we already know is mistyped is how the validator ends up
        # raising on the very input it exists to reject.
        raise ConfigurationInvalid(" ".join(problems))

    problems = validate_config(merged)
    if problems:
        raise ConfigurationInvalid(" ".join(problems))
    return merged


def preview_config(payload: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Merge -> coerce, WITHOUT raising. The entry point for an unsaved config.

    Preview exists for a config the operator is still editing, so it must not
    refuse an incomplete one the way ``prepare_config`` does. But it must go
    through the same coercion, or it prices something different from what the
    save will: clearing a band's percentage is repaired on save and used to
    500 the preview, so the panel silently blanked while Save succeeded.

    Returns the problems instead of raising, so the operator can be told which
    field needs attention rather than watching the panel disappear.
    """
    merged = merge_config(payload)
    # repair=True: an uncoercible LEAF falls back to its default so the preview
    # can still render. Reporting alone was not enough -- the bad value stayed in
    # place and the engine 500'd on it, which is the blank panel all over again.
    merged, problems = coerce_config(merged, repair=True)
    try:
        problems += validate_config(merged)
    except Exception as exc:  # noqa: BLE001 - preview must never raise
        problems.append(f"Configuration could not be fully checked: {exc}")

    if problems:
        # Some faults cannot be repaired leaf-by-leaf: an operator-authored band
        # has no shipped default to fall back to, and a malformed anchors list
        # has no usable member. Restore the whole affected SECTION so the panel
        # still renders -- the problems above already say what was wrong, and a
        # preview that vanishes teaches the operator nothing.
        shipped = default_config()
        for section in {p.split(".")[0].split("[")[0] for p in _problem_paths(problems)}:
            if section in shipped:
                merged[section] = shipped[section]

    return merged, problems


def _problem_paths(problems: list[str]) -> list[str]:
    """The leading dotted path from each problem message, where there is one."""
    paths = []
    for problem in problems:
        head = problem.split(" ", 1)[0]
        if "." in head or "[" in head:
            paths.append(head)
    return paths
