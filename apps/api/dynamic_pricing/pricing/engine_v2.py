"""PricingEngineV2 — validated rate band + bounded dynamic layer.

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
from .registry import register_engine


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


def _round_rate(value: float, increment: float, mode: str = "nearest") -> float:
    if not increment or increment <= 0:
        return round(value, 2)
    q = value / increment
    if mode == "up":
        return math.ceil(q) * increment
    if mode == "down":
        return math.floor(q) * increment
    return math.floor(q + 0.5) * increment  # explicit half-up


class PricingEngineV2(PricingEngine):
    name = "Pricing Engine V2 (rate-band anchored)"
    version = "v2.0.0"
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
                label=f"Seasonal base rate — {context.season_label or 'unknown season'}",
                price_before=base_net,
                price_after=base_net,
                delta=0.0,
                adjustment_pct=0.0,
                factor=1.0,
                reason=(
                    f"{context.room_category_label} in {context.season_label}: "
                    f"BASE {base_net:,.0f} {context.currency} NET "
                    f"(band {band_min:,.0f}–{band_max:,.0f}). "
                    f"Source: {context.rate_band_source}."
                    + (f" {context.season_note}" if context.season_note else "")
                )
                if band_min is not None and band_max is not None
                else f"Base {base_net:,.0f} {context.currency} NET.",
            )
        )

        # ---- the dynamic layer -------------------------------------------
        contributions: list[tuple[str, str, float, str, bool, bool]] = []
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

        raw_total = sum(c[2] for c in contributions if not c[5])  # exclude ignored

        dyn = cfg.get("dynamic", {})
        lo = float(dyn.get("min_total_adjustment_pct", -15.0))
        hi = float(dyn.get("max_total_adjustment_pct", 15.0))
        bounded_total = min(max(raw_total, lo), hi)
        bound_hit = abs(bounded_total - raw_total) > 1e-9

        # Scale each contribution proportionally so the displayed lines still
        # sum to the applied total — otherwise the breakdown would not add up.
        scale = (bounded_total / raw_total) if (bound_hit and raw_total) else 1.0

        running = base_net
        for code, label, pct, reason, neutral, ignored in contributions:
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
                    reason=reason,
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
                    price_before=round(running, 2),
                    price_after=round(running, 2),
                    delta=0.0,
                    adjustment_pct=0.0,
                    factor=1.0,
                    reason=(
                        f"Signals totalled {raw_total:+.1f}%, beyond the configured limit of "
                        f"{lo:+.0f}%…{hi:+.0f}%. Scaled back to {bounded_total:+.1f}% so no single "
                        f"run can move the rate too far."
                    ),
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
                    reason=(
                        f"Dynamic layer would have priced below the validated seasonal floor of "
                        f"{band_min:,.0f} {context.currency} NET. Raised to the floor."
                    ),
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
                    reason=(
                        f"Dynamic layer would have priced above the validated seasonal ceiling of "
                        f"{band_max:,.0f} {context.currency} NET. Reduced to the ceiling."
                    ),
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
                    reason=f"Rounded to the nearest {int(increment):,} {context.currency}."
                    if increment
                    else "Rounded.",
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
            "ignored_signals": [c[0] for c in contributions if c[5]],
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
            explanation=self._explain(context, adjustments, recommended, bounded_total),
            engine_version=self.version,
            metadata=metadata,
        )

    # ------------------------------------------------------------- signals
    # Each returns (code, label, adjustment_pct, reason, is_neutral, is_ignored)

    def _pace(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("pace", {})
        if not node.get("enabled", True):
            return None
        if ctx.pace_gap is None:
            reason = (
                "Booking pace unavailable; no pace adjustment applied."
                if ctx.expected_occupancy is None
                else "Occupancy unavailable; no pace adjustment applied."
            )
            return ("pace", "Pace position", 0.0, reason, True, False)

        band = _band_for(ctx.pace_gap, node.get("bands", []), "max_gap")
        if band is None:
            return ("pace", "Pace position", 0.0, "No pace band configured.", True, False)
        pct = float(band.get("adjustment_pct", 0.0))
        direction = "ahead of" if ctx.pace_gap > 0 else "behind"
        return (
            "pace",
            f"{band.get('label', 'Pace position')}",
            pct,
            (
                f"{ctx.occupancy:.0%} sold with {ctx.days_to_arrival} day(s) to arrival. "
                f"The booking curve expects {ctx.expected_occupancy:.0%} by now, so this date is "
                f"{abs(ctx.pace_gap) * 100:.0f} points {direction} pace."
            ),
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
                0.0,
                "No booking history for this room type; no pickup adjustment applied.",
                True,
                False,
            )
        band = _band_for(ctx.pickup_delta, node.get("bands", []), "max_delta", inclusive=True)
        if band is None:
            return ("recent_pickup", "Recent pickup", 0.0, "No pickup band configured.", True, False)
        pct = float(band.get("adjustment_pct", 0.0))
        return (
            "recent_pickup",
            band.get("label", "Recent pickup"),
            pct,
            (
                f"{ctx.recent_pickup:.0f} booking(s) in the last "
                f"{int(node.get('lookback_days', 7))} days versus {ctx.expected_pickup:.1f} expected "
                f"({ctx.pickup_delta:+.1f})."
            ),
            abs(pct) < 1e-9,
            False,
        )

    def _event(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("event", {})
        if not node.get("enabled", True) or not ctx.is_event:
            return None
        if ctx.event_adjustment_pct is not None:
            pct = float(ctx.event_adjustment_pct)
            basis = "event-specific override"
        else:
            level = (ctx.event_impact_level or "medium").lower()
            pct = float(node.get("impact_adjustment_pct", {}).get(level, 0.0))
            basis = f"{level} impact level"
        return (
            "event",
            f"Event: {ctx.event_name}",
            pct,
            f"'{ctx.event_name}' falls on this stay date ({basis}).",
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
                "Market signal (ignored — low confidence)",
                0.0,
                (
                    f"{ctx.market_ignored_count} observation(s) found but none met the {gate} "
                    f"confidence bar, so the market did not move this rate. Generic web prices "
                    f"lack stay-date, length-of-stay and tax/fee basis, and are not comparable to "
                    f"a NET rate."
                ),
                False,
                True,
            )

        if ctx.market_price_index is None or ctx.market_qualified_count < min_obs:
            reason = "Market signal unavailable; no market adjustment applied."
            if 0 < ctx.market_qualified_count < min_obs:
                reason = (
                    f"Only {ctx.market_qualified_count} qualified observation(s) "
                    f"(minimum {min_obs}); no market adjustment applied."
                )
            return ("market", "Market signal", 0.0, reason, True, False)

        sensitivity = float(node.get("sensitivity", 0.5))
        cap = float(node.get("max_adjustment_pct", 5.0))
        raw = sensitivity * (ctx.market_price_index - 1.0) * 100.0
        pct = min(max(raw, -cap), cap)

        direction = "above" if ctx.market_price_index > 1 else "below"
        capped = f" (capped from {raw:+.1f}%)" if abs(pct - raw) > 1e-9 else ""
        return (
            "market",
            "Market signal",
            pct,
            (
                f"Comparable rate {ctx.market_reference_net_rate:,.0f} {ctx.currency} is "
                f"{abs(ctx.market_price_index - 1) * 100:.0f}% {direction} the comp-set baseline "
                f"({ctx.market_qualified_count} × {ctx.market_confidence}-confidence "
                f"observation(s), sensitivity {sensitivity:.2f}){capped}."
            ),
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
            ctx.day_of_week.capitalize(),
            pct,
            f"{ctx.day_of_week.capitalize()} carries a {pct:+.1f}% structural adjustment.",
            False,
            False,
        )

    # --------------------------------------------------------- explanation
    def _explain(
        self,
        ctx: PricingContext,
        adjustments: list[Adjustment],
        recommended: float,
        total_pct: float,
    ) -> str:
        parts: list[str] = []
        opening = (
            f"{ctx.room_category_label} on {ctx.stay_date:%a %d %b} sits in "
            f"{ctx.season_label or 'an unknown season'}, where the validated BASE NET rate is "
            f"{ctx.band_base_net_rate:,.0f} {ctx.currency}."
            if ctx.band_base_net_rate
            else f"Base NET rate {ctx.current_net_rate:,.0f} {ctx.currency}."
        )
        parts.append(opening)

        applied = [
            a
            for a in adjustments
            if a.code not in ("rate_band", "rounding", "dynamic_bound")
            and not a.is_neutral
            and not a.is_ignored
        ]
        if applied:
            moves = [
                f"{a.label} ({a.adjustment_pct:+.1f}%, {a.delta:+,.0f})" for a in applied
            ]
            parts.append("Dynamic signals: " + "; ".join(moves) + ".")
        else:
            parts.append("No dynamic signal moved this date away from its seasonal base rate.")

        clamped = [a for a in adjustments if a.code in ("band_min_clamp", "band_max_clamp")]
        if clamped:
            parts.append(clamped[0].reason)

        ignored = [a for a in adjustments if a.is_ignored]
        if ignored:
            parts.append(ignored[0].reason)

        blind = [
            a.reason
            for a in adjustments
            if a.is_neutral and a.code in ctx.missing and a.reason
        ]
        if blind:
            parts.append(" ".join(blind))

        parts.append(
            f"Recommended NET rate {recommended:,.0f} {ctx.currency} "
            f"({total_pct:+.1f}% dynamic on base)."
        )
        return " ".join(parts)


register_engine("v2", PricingEngineV2)
