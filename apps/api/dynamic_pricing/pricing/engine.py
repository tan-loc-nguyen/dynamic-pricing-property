"""RateBandPricingEngine — validated rate band + bounded dynamic layer.

    band          = SeasonalRateBook.lookup(room_category, stay_date)   [VALIDATED]
    base_net      = band.base
    delta_pct     = pace + recent_pickup + event + qualified_market [+ day_of_week]
    delta_pct     = clamp(delta_pct, dynamic.min, dynamic.max)
    recommended   = clamp(base_net * (1 + delta_pct/100), band.min, band.max)
                  -> rounding

Deliberate design choices:

* **The season is not multiplied.** It selects the band. The client's table
  already encodes seasonality, so applying a seasonality factor on top would
  double-count it. There is no season factor in this engine.

* **Additive, not multiplicative.** Each signal contributes percentage points
  of the BASE rate. Four stacked multipliers compound unpredictably; four
  additive percentages are bounded and an operator can add them up by hand.

* **No independent occupancy or lead-time factor.** Occupancy only means
  something relative to how far out the date is, so both are folded into one
  signal: pace position (actual vs. expected occupancy for this lead time).
  Rewarding occupancy, lead time and pace separately would pay three times for
  one demand condition.

* **Low-confidence market data cannot move the price.** It is surfaced as an
  ignored line so the operator sees it was considered and why it was excluded.

This formula is NOT claimed to be optimal. Every threshold is UNVALIDATED.
"""

from __future__ import annotations

import math
from typing import Any

from ..features.context import PricingContext
from .base import Adjustment, PricingEngine, PricingResult
from .rate_book import RATE_BOOK_SOURCE
from .registry import register_engine

# Every message key this engine can emit. The locale files are checked
# against this, so a missing translation fails a test rather than a demo.
EMITTABLE_MESSAGE_KEYS: tuple[str, ...] = (
    "adjustments.rate_band",
    "adjustments.pace.well_behind",
    "adjustments.pace.behind",
    "adjustments.pace.on_pace",
    "adjustments.pace.ahead",
    "adjustments.pace.well_ahead",
    "adjustments.pace.unavailable",
    "adjustments.pace.occupancy_unavailable",
    "adjustments.pace.no_band",
    "adjustments.recent_pickup.stalled",
    "adjustments.recent_pickup.slowing",
    "adjustments.recent_pickup.as_expected",
    "adjustments.recent_pickup.accelerating",
    "adjustments.recent_pickup.surging",
    "adjustments.recent_pickup.unavailable",
    "adjustments.recent_pickup.no_band",
    "adjustments.event.level",
    "adjustments.event.override",
    "adjustments.market.applied",
    "adjustments.market.ignored_low_confidence",
    "adjustments.market.unavailable",
    "adjustments.market.insufficient",
    "adjustments.day_of_week",
    "adjustments.dynamic_bound",
    "adjustments.band_min_clamp",
    "adjustments.band_max_clamp",
    "adjustments.rounding",
)


def _band_for(
    value: float, bands: list[dict[str, Any]], key: str, inclusive: bool = False
) -> dict[str, Any] | None:
    """First band whose threshold the value falls under. Bands are ordered.

    ``inclusive=True`` is required for pickup bands, whose lowest reachable
    value sits exactly ON a threshold: recent pickup cannot go below zero, so
    the smallest possible delta is exactly -expected_pickup. With a strict `<`
    the "stalled" band could never be selected and a date with no bookings at
    all was reported as merely "slowing".
    """
    for band in bands:
        threshold = band.get(key)
        if threshold is None:
            continue
        limit = float(threshold)
        if (value <= limit) if inclusive else (value < limit):
            return band
    return bands[-1] if bands else None


def _tone_for(contribution: tuple | None) -> str:
    """A signal's direction, from the adjustment its band actually applies."""
    if contribution is None:
        return "neutral"
    _code, _label, _key, pct, _params, neutral, ignored = contribution
    if ignored or neutral and abs(pct) < 1e-9 and _key and _key.endswith(
        ("unavailable", "no_band", "occupancy_unavailable")
    ):
        return "neutral"
    if pct < -1e-9:
        return "down"
    if pct > 1e-9:
        return "up"
    return "info"


def _round_rate(value: float, increment: float, mode: str = "nearest") -> float:
    if not increment or increment <= 0:
        return round(value, 2)
    q = value / increment
    if mode == "up":
        return math.ceil(q) * increment
    if mode == "down":
        return math.floor(q) * increment
    return math.floor(q + 0.5) * increment  # explicit half-up


class RateBandPricingEngine(PricingEngine):
    name = "Rate-band pricing engine"
    # Recorded on every recommendation and decision, so a past price can always
    # be traced to the logic that produced it.
    version = "1.0.0"
    description = (
        "Anchors on the client-validated seasonal MIN/BASE/MAX NET rate band, then "
        "applies a bounded additive dynamic layer: pace position, recent pickup, "
        "events and qualified market evidence. Seasonality is not re-applied. "
        "Dynamic thresholds are UNVALIDATED."
    )

    def calculate(self, context: PricingContext, configuration: dict[str, Any]) -> PricingResult:
        cfg = configuration or {}

        base_net = float(context.band_base_net_rate or context.current_net_rate or 0.0)
        band_min = context.band_min_net_rate
        band_max = context.band_max_net_rate

        adjustments: list[Adjustment] = []

        # ---- step 0: the validated anchor, always shown first -------------
        adjustments.append(
            Adjustment(
                code="rate_band",
                label=context.season_label or "",
                label_key="adjustments.rate_band",
                price_before=base_net,
                price_after=base_net,
                delta=0.0,
                adjustment_pct=0.0,
                factor=1.0,
                params={
                    "season_key": context.season_key,
                    "room_category": context.room_category,
                    "stay_date": context.stay_date.isoformat(),
                    "base_net_rate": base_net,
                    "min_net_rate": band_min,
                    "max_net_rate": band_max,
                    "currency": context.currency,
                    "source": context.rate_band_source,
                    "rate_basis": "NET",
                    # Provenance, NOT "are there numbers". The feature engine
                    # substitutes the room type's fallback rates when no band
                    # covers a date, and those columns are NOT NULL -- so a
                    # has-numbers test is always true and would describe a
                    # guess in the shape of a validated band.
                    "has_validated_band": context.rate_band_source == RATE_BOOK_SOURCE,
                },
            )
        )

        # ---- the dynamic layer -------------------------------------------
        # (code, label, label_key, pct, params, is_neutral, is_ignored)
        contributions: list[tuple[str, str, str | None, float, dict, bool, bool]] = []
        for producer in (
            self._pace,
            self._recent_pickup,
            self._event,
            self._market,
            self._day_of_week,
        ):
            result = producer(context, cfg)
            if result is not None:
                contributions.append(result)

        raw_total = sum(c[3] for c in contributions if not c[6])  # exclude ignored

        dyn = cfg.get("dynamic", {})
        lo = float(dyn.get("min_total_adjustment_pct", -15.0))
        hi = float(dyn.get("max_total_adjustment_pct", 15.0))
        bounded_total = min(max(raw_total, lo), hi)
        bound_hit = abs(bounded_total - raw_total) > 1e-9

        # Scale each contribution proportionally so the displayed lines still
        # sum to the applied total — otherwise the breakdown would not add up.
        scale = (bounded_total / raw_total) if (bound_hit and raw_total) else 1.0

        running = base_net
        for code, label, label_key, pct, params, neutral, ignored in contributions:
            applied_pct = 0.0 if ignored else pct * scale
            before = running
            after = before + base_net * (applied_pct / 100.0)
            adjustments.append(
                Adjustment(
                    code=code,
                    label=label,
                    price_before=round(before, 2),
                    price_after=round(after, 2) if not ignored else round(before, 2),
                    delta=round(after - before, 2) if not ignored else 0.0,
                    adjustment_pct=round(applied_pct, 4),
                    factor=round(after / before, 9) if before and not ignored else 1.0,
                    label_key=label_key,
                    params=params,
                    is_neutral=neutral,
                    is_ignored=ignored,
                )
            )
            if not ignored:
                running = after

        if bound_hit:
            adjustments.append(
                Adjustment(
                    code="dynamic_bound",
                    label="Total adjustment bound",
                    label_key="adjustments.dynamic_bound",
                    price_before=round(running, 2),
                    price_after=round(running, 2),
                    delta=0.0,
                    adjustment_pct=0.0,
                    factor=1.0,
                    params={
                        "raw_pct": round(raw_total, 4),
                        "bounded_pct": round(bounded_total, 4),
                        "min_pct": lo,
                        "max_pct": hi,
                    },
                )
            )

        net_rate_before_clamp = running

        # ---- clamp into the VALIDATED band -------------------------------
        clamp_applied: str | None = None
        if band_min is not None and running < band_min:
            before = running
            running = float(band_min)
            clamp_applied = "min"
            adjustments.append(
                Adjustment(
                    code="band_min_clamp",
                    label="Seasonal MIN floor",
                    price_before=round(before, 2),
                    price_after=round(running, 2),
                    delta=round(running - before, 2),
                    adjustment_pct=0.0,
                    factor=round(running / before, 9) if before else 1.0,
                    label_key="adjustments.band_min_clamp",
                    params={
                        "bound_net_rate": float(band_min),
                        "unclamped_net_rate": round(before, 2),
                        "currency": context.currency,
                    },
                )
            )
        elif band_max is not None and running > band_max:
            before = running
            running = float(band_max)
            clamp_applied = "max"
            adjustments.append(
                Adjustment(
                    code="band_max_clamp",
                    label="Seasonal MAX ceiling",
                    price_before=round(before, 2),
                    price_after=round(running, 2),
                    delta=round(running - before, 2),
                    adjustment_pct=0.0,
                    factor=round(running / before, 9) if before else 1.0,
                    label_key="adjustments.band_max_clamp",
                    params={
                        "bound_net_rate": float(band_max),
                        "unclamped_net_rate": round(before, 2),
                        "currency": context.currency,
                    },
                )
            )

        # ---- rounding ------------------------------------------------------
        rounding_cfg = cfg.get("rounding", {})
        increment = float(rounding_cfg.get("increment", 0) or 0)
        mode = str(rounding_cfg.get("mode", "nearest"))
        rounded = _round_rate(running, increment, mode)

        # Rounding must never push the rate back outside the validated band.
        if band_min is not None and rounded < band_min:
            rounded = _round_rate(float(band_min), increment, "up")
        if band_max is not None and rounded > band_max:
            rounded = _round_rate(float(band_max), increment, "down")

        if abs(rounded - running) > 1e-9:
            before = running
            adjustments.append(
                Adjustment(
                    code="rounding",
                    label="Rounding",
                    price_before=round(before, 2),
                    price_after=round(rounded, 2),
                    delta=round(rounded - before, 2),
                    adjustment_pct=0.0,
                    factor=round(rounded / before, 9) if before else 1.0,
                    label_key="adjustments.rounding",
                    params={"increment": increment, "currency": context.currency},
                )
            )
            running = rounded

        recommended = round(running, 2)
        applied_total_pct = (
            round((recommended - base_net) / base_net * 100, 4) if base_net else 0.0
        )

        metadata = {
            "engine": self.name,
            "mode": cfg.get("mode", "shadow"),
            "rate_basis": "NET",
            "season_key": context.season_key,
            "rate_band_source": context.rate_band_source,
            "band_min_net_rate": band_min,
            "band_base_net_rate": base_net,
            "band_max_net_rate": band_max,
            "raw_dynamic_pct": round(raw_total, 4),
            "bounded_dynamic_pct": round(bounded_total, 4),
            "dynamic_bound_applied": bound_hit,
            "clamp_applied": clamp_applied,
            "rounding_increment": increment,
            "missing_signals": list(context.missing),
            "ignored_signals": [c[0] for c in contributions if c[6]],
            # The band this run selected, carried on the recommendation itself so
            # the list view can label a row without loading its adjustments -- and
            # without re-deriving the band from thresholds in the frontend (D28).
            "pace_label_key": next((c[2] for c in contributions if c[0] == "pace"), None),
            "pickup_label_key": next(
                (c[2] for c in contributions if c[0] == "recent_pickup"), None
            ),
            # ...and the wording itself, for a band the operator named: there is
            # no message key for it, and the row must still show what the drawer
            # shows rather than falling back to "no data".
            "pace_label": next((c[1] for c in contributions if c[0] == "pace"), None),
            "pickup_label": next((c[1] for c in contributions if c[0] == "recent_pickup"), None),
            # The chip's COLOUR, decided by the same band that decided its text.
            # TypeScript used to re-derive this from hardcoded ±0.08 thresholds,
            # so widening a band produced a green chip reading "On pace" -- D28
            # again, in the channel nobody was watching. Reading the band's own
            # adjustment also works for a band the operator invented, which
            # TypeScript has no thresholds for at all.
            "pace_tone": _tone_for(next((c for c in contributions if c[0] == "pace"), None)),
            "booking_curve": context.booking_curve_source,
            "booking_curve_validated": context.booking_curve_validated,
            "dynamic_assumptions_status": "UNVALIDATED",
            "rate_band_status": context.rate_band_source,
        }

        return PricingResult(
            recommended_net_rate=recommended,
            base_net_rate=round(base_net, 2),
            current_net_rate=round(context.current_net_rate, 2),
            net_rate_before_clamp=round(net_rate_before_clamp, 2),
            total_adjustment_pct=applied_total_pct,
            adjustments=adjustments,
            engine_version=self.version,
            metadata=metadata,
        )

    # ------------------------------------------------------------- signals
    # Each returns (code, label, label_key, adjustment_pct, params,
    # is_neutral, is_ignored).
    #
    # No producer composes a sentence. They emit the key that names the
    # sentence and the figures it interpolates, so the same calculation reads
    # correctly in English and Vietnamese.

    @staticmethod
    def _band_identity(band: dict, section: str, fallback_label: str) -> tuple[str, str | None]:
        """(label, message key) for a band.

        A SHIPPED band carries a stable ``key`` that the locale files translate.
        A band the operator invented or a label they retyped has no key, so its
        own wording is returned verbatim -- mistranslating it into a
        neighbouring band's copy would put words in the operator's mouth.
        """
        label = str(band.get("label") or fallback_label)
        key = band.get("key")
        return label, f"adjustments.{section}.{key}" if key else None

    def _pace(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("pace", {})
        if not node.get("enabled", True):
            return None
        if ctx.pace_gap is None:
            key = (
                "adjustments.pace.unavailable"
                if ctx.expected_occupancy is None
                else "adjustments.pace.occupancy_unavailable"
            )
            return ("pace", "Pace position", key, 0.0, {}, True, False)

        band = _band_for(ctx.pace_gap, node.get("bands", []), "max_gap")
        if band is None:
            return ("pace", "Pace position", "adjustments.pace.no_band", 0.0, {}, True, False)
        pct = float(band.get("adjustment_pct", 0.0))
        label, key = self._band_identity(band, "pace", "Pace position")
        return (
            "pace",
            label,
            key,
            pct,
            {
                "occupancy": ctx.occupancy,
                "expected_occupancy": ctx.expected_occupancy,
                "days_to_arrival": ctx.days_to_arrival,
                "gap_pp": round(abs(ctx.pace_gap) * 100, 1),
                "direction": "ahead" if ctx.pace_gap > 0 else "behind",
            },
            abs(pct) < 1e-9,
            False,
        )

    def _recent_pickup(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("recent_pickup", {})
        if not node.get("enabled", True):
            return None
        if ctx.pickup_delta is None:
            return (
                "recent_pickup",
                "Recent pickup",
                "adjustments.recent_pickup.unavailable",
                0.0,
                {},
                True,
                False,
            )
        band = _band_for(ctx.pickup_delta, node.get("bands", []), "max_delta", inclusive=True)
        if band is None:
            return (
                "recent_pickup",
                "Recent pickup",
                "adjustments.recent_pickup.no_band",
                0.0,
                {},
                True,
                False,
            )
        pct = float(band.get("adjustment_pct", 0.0))
        label, key = self._band_identity(band, "recent_pickup", "Recent pickup")
        return (
            "recent_pickup",
            label,
            key,
            pct,
            {
                "recent_pickup": ctx.recent_pickup,
                "expected_pickup": ctx.expected_pickup,
                "delta": ctx.pickup_delta,
                "lookback_days": int(node.get("lookback_days", 7)),
            },
            abs(pct) < 1e-9,
            False,
        )

    def _event(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("event", {})
        if not node.get("enabled", True) or not ctx.is_event:
            return None
        if ctx.event_adjustment_pct is not None:
            pct = float(ctx.event_adjustment_pct)
            key = "adjustments.event.override"
            level = None
        else:
            level = (ctx.event_impact_level or "medium").lower()
            pct = float(node.get("impact_adjustment_pct", {}).get(level, 0.0))
            key = "adjustments.event.level"
        return (
            "event",
            ctx.event_name or "",
            key,
            pct,
            {"event_name": ctx.event_name, "impact_level": level},
            abs(pct) < 1e-9,
            False,
        )

    def _market(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("market", {})
        if not node.get("enabled", True):
            return None

        min_obs = int(node.get("min_observations", 2))
        gate = str(node.get("min_confidence", "MEDIUM")).upper()

        # Observed but excluded by the confidence gate -> show, do not apply.
        if ctx.market_qualified_count == 0 and ctx.market_ignored_count > 0:
            return (
                "market",
                "Market signal",
                "adjustments.market.ignored_low_confidence",
                0.0,
                {"ignored_count": ctx.market_ignored_count, "gate": gate},
                False,
                True,
            )

        if ctx.market_price_index is None or ctx.market_qualified_count < min_obs:
            key = "adjustments.market.unavailable"
            params: dict = {}
            if 0 < ctx.market_qualified_count < min_obs:
                key = "adjustments.market.insufficient"
                params = {"qualified_count": ctx.market_qualified_count, "min_observations": min_obs}
            return ("market", "Market signal", key, 0.0, params, True, False)

        sensitivity = float(node.get("sensitivity", 0.5))
        cap = float(node.get("max_adjustment_pct", 5.0))
        raw = sensitivity * (ctx.market_price_index - 1.0) * 100.0
        pct = min(max(raw, -cap), cap)

        return (
            "market",
            "Market signal",
            "adjustments.market.applied",
            pct,
            {
                "reference_net_rate": ctx.market_reference_net_rate,
                "currency": ctx.currency,
                "delta_pct": round(abs(ctx.market_price_index - 1) * 100, 1),
                "direction": "above" if ctx.market_price_index > 1 else "below",
                "qualified_count": ctx.market_qualified_count,
                "confidence": ctx.market_confidence,
                "sensitivity": sensitivity,
                "was_capped": abs(pct - raw) > 1e-9,
                "raw_pct": round(raw, 4),
            },
            abs(pct) < 1e-9,
            False,
        )

    def _day_of_week(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("day_of_week", {})
        if not node.get("enabled", False):
            return None  # OFF by default until Luminous confirms a weekday pattern
        if not ctx.day_of_week:
            return None
        pct = float(node.get("adjustment_pct", {}).get(ctx.day_of_week, 0.0))
        if abs(pct) < 1e-9:
            return None
        return (
            "day_of_week",
            ctx.day_of_week,
            "adjustments.day_of_week",
            pct,
            {"day": ctx.day_of_week, "pct": pct},
            False,
            False,
        )


# Registered under a neutral key. The registry is the pluggability seam: a
# finance-authored engine registers alongside this one and becomes the
# default without touching the UI, database, providers or history.
register_engine("default", RateBandPricingEngine)
