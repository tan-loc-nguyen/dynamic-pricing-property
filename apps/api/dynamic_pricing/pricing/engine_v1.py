"""PricingEngineV1 — LEGACY multiplicative engine, retained for comparison.

SUPERSEDED BY PricingEngineV2. Kept registered so the engine registry is
demonstrably pluggable and so V1 and V2 can be compared side by side.

Migrated to the RoomType/NET-rate context. Two deliberate changes:
  * its seasonality factor has been REMOVED — the validated rate band now
    encodes season, so multiplying one on top would double-count it;
  * its day-of-week factor is neutral by default (unvalidated).
It reads its own isolated config under the "legacy_v1" key.

Original description follows.


    recommended = base
                  x day-of-week
                  x occupancy
                  x booking pace
                  x lead time (incl. urgency interaction)
                  x season
                  x event
                  x market
      -> compounding guardrail -> min/max bounds -> rounding

This formula is a DEMO SCAFFOLD. It is not claimed to be optimal, or even
correct for Luminous. Every constant it reads comes from the configuration
payload (see pricing/defaults.py), so replacing the business rules is a
Settings change, not a code change.

No randomness, no wall-clock reads, no I/O: same inputs -> same output.
"""

from __future__ import annotations

from typing import Any

from ..features.context import PricingContext
from .base import Adjustment, PricingEngine, PricingResult
from .registry import register_engine

# Human-readable names for the neutral-fallback explanations.
_MISSING_COPY = {
    "occupancy": "Occupancy unavailable; no occupancy adjustment applied.",
    "recent_pickup": "Booking pace unavailable; no pace adjustment applied.",
    "lead_time": "Days-to-check-in unavailable; no lead-time adjustment applied.",
    "market": "Market signal unavailable; no market adjustment applied.",
    "day_of_week": "Day of week unavailable; no weekday adjustment applied.",
    "season": "Season unavailable; no seasonal adjustment applied.",
}


def _band_for(
    value: float,
    bands: list[dict[str, Any]],
    key: str = "max",
    inclusive: bool = False,
) -> dict[str, Any] | None:
    """First band whose threshold the value falls under. Bands are ordered.

    ``inclusive=False`` (occupancy, pace): ``max: 0.30`` means "below 30%".
    ``inclusive=True``  (lead time):       ``max_days: 3`` means "3 days or fewer".
    The two families genuinely differ -- a continuous ratio vs a whole-day
    count -- so the semantics are named rather than fudged with an offset.
    """
    for band in bands:
        threshold = band.get(key)
        if threshold is None:
            continue
        limit = float(threshold)
        if (value <= limit) if inclusive else (value < limit):
            return band
    return bands[-1] if bands else None


def _round_price(price: float, increment: float, mode: str = "nearest") -> float:
    if not increment or increment <= 0:
        return round(price, 2)
    quotient = price / increment
    if mode == "up":
        import math

        return math.ceil(quotient) * increment
    if mode == "down":
        import math

        return math.floor(quotient) * increment
    # "nearest" with explicit half-up so results never depend on float banker's rounding
    import math

    return math.floor(quotient + 0.5) * increment


class PricingEngineV1(PricingEngine):
    name = "Pricing Engine V1 (demo)"
    version = "v1.0.0"
    description = (
        "Deterministic multiplicative model with per-factor bands, a compounding "
        "guardrail, min/max bounds and rounding. All constants are configurable. "
        "Assumptions are UNVALIDATED."
    )

    # ------------------------------------------------------------------ API
    def calculate(self, context: PricingContext, configuration: dict[str, Any]) -> PricingResult:
        cfg = (configuration or {}).get("legacy_v1", {}) or {}
        pricing_cfg = cfg.get("pricing", {})

        base_price = self._resolve_base_price(context, pricing_cfg)
        running = base_price
        adjustments: list[Adjustment] = []

        def step(code: str, label: str, factor: float, reason: str, neutral: bool = False) -> None:
            nonlocal running
            before = running
            after = before * factor
            adjustments.append(
                Adjustment(
                    code=code,
                    label=label,
                    # 9dp keeps `price_before x factor == price_after` true to the
                    # cent, so an operator can re-derive any line by hand.
                    factor=round(factor, 9),
                    adjustment_pct=round((factor - 1) * 100, 4),
                    price_before=round(before, 2),
                    price_after=round(after, 2),
                    delta=round(after - before, 2),
                    reason=reason,
                    is_neutral=neutral,
                )
            )
            running = after

        for producer in (
            self._factor_day_of_week,
            self._factor_occupancy,
            self._factor_booking_pace,
            self._factor_lead_time,
            self._factor_urgency,
            self._factor_event,
            self._factor_market,
        ):
            result = producer(context, cfg)
            if result is not None:
                step(*result)

        raw_multiplier = running / base_price if base_price else 1.0

        # ---- compounding guardrail (A5) --------------------------------
        lo = float(pricing_cfg.get("global_multiplier_min", 0.70))
        hi = float(pricing_cfg.get("global_multiplier_max", 1.60))
        clamped_multiplier = min(max(raw_multiplier, lo), hi)
        guardrail_hit = abs(clamped_multiplier - raw_multiplier) > 1e-9
        if guardrail_hit:
            correction = clamped_multiplier / raw_multiplier if raw_multiplier else 1.0
            direction = "capped" if clamped_multiplier < raw_multiplier else "lifted"
            step(
                "compounding_guardrail",
                "Compounding guardrail",
                correction,
                f"Combined factors reached x{raw_multiplier:.3f}; {direction} to the configured "
                f"limit of x{clamped_multiplier:.2f} to avoid runaway compounding.",
            )

        price_before_bounds = running

        # ---- min / max bounds (A2/A3) -----------------------------------
        min_price = self._resolve_min_price(context, pricing_cfg)
        max_price = self._resolve_max_price(context, pricing_cfg)
        bounds_applied: str | None = None

        if min_price is not None and running < min_price:
            factor = min_price / running if running else 1.0
            step(
                "min_price_floor",
                "Minimum price floor",
                factor,
                f"Calculated price fell below the configured floor; raised to the minimum.",
            )
            bounds_applied = "min"
        elif max_price is not None and running > max_price:
            factor = max_price / running if running else 1.0
            step(
                "max_price_cap",
                "Maximum price cap",
                factor,
                f"Calculated price exceeded the configured ceiling; reduced to the maximum.",
            )
            bounds_applied = "max"

        # ---- rounding (A4) ----------------------------------------------
        increment = float(pricing_cfg.get("rounding_increment", 0) or 0)
        mode = str(pricing_cfg.get("rounding_mode", "nearest"))
        rounded = _round_price(running, increment, mode)

        # Rounding must never push the price back outside the bounds.
        if min_price is not None and rounded < min_price:
            rounded = _round_price(min_price, increment, "up")
        if max_price is not None and rounded > max_price:
            rounded = _round_price(max_price, increment, "down")

        if abs(rounded - running) > 1e-9:
            factor = rounded / running if running else 1.0
            step(
                "rounding",
                "Rounding",
                factor,
                f"Rounded to the nearest {int(increment):,} {context.currency}."
                if increment
                else "Rounded.",
            )

        recommended = round(running, 2)
        total_multiplier = recommended / base_price if base_price else 1.0

        metadata = {
            "engine": self.name,
            "raw_multiplier": round(raw_multiplier, 6),
            "clamped_multiplier": round(clamped_multiplier, 6),
            "guardrail_applied": guardrail_hit,
            "bounds_applied": bounds_applied,
            "min_price": min_price,
            "max_price": max_price,
            "rounding_increment": increment,
            "missing_signals": list(context.missing),
            "assumptions_status": "UNVALIDATED",
        }

        return PricingResult(
            recommended_net_rate=recommended,
            base_net_rate=round(base_price, 2),
            current_net_rate=round(context.current_net_rate, 2),
            net_rate_before_clamp=round(price_before_bounds, 2),
            total_adjustment_pct=round((total_multiplier - 1) * 100, 4),
            adjustments=adjustments,
            explanation=self._build_explanation(context, adjustments, recommended),
            engine_version=self.version,
            metadata=metadata,
        )

    # -------------------------------------------------------------- helpers
    def _resolve_base_price(self, ctx: PricingContext, pricing_cfg: dict) -> float:
        override = pricing_cfg.get("base_price_override")
        if override:
            return float(override)
        if ctx.band_base_net_rate:
            return float(ctx.band_base_net_rate)
        return float(ctx.current_net_rate or 0.0)

    def _resolve_min_price(self, ctx: PricingContext, pricing_cfg: dict) -> float | None:
        override = pricing_cfg.get("min_price_override")
        if override:
            return float(override)
        return float(ctx.band_min_net_rate) if ctx.band_min_net_rate else None

    def _resolve_max_price(self, ctx: PricingContext, pricing_cfg: dict) -> float | None:
        override = pricing_cfg.get("max_price_override")
        if override:
            return float(override)
        return float(ctx.band_max_net_rate) if ctx.band_max_net_rate else None

    # -------------------------------------------------------------- factors
    # Each returns (code, label, factor, reason, is_neutral) or None to skip.

    def _factor_day_of_week(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("day_of_week", {})
        if not node.get("enabled", True):
            return None
        if not ctx.day_of_week:
            return ("day_of_week", "Day of week", 1.0, _MISSING_COPY["day_of_week"], True)
        multipliers = node.get("multipliers", {})
        factor = float(multipliers.get(ctx.day_of_week, 1.0))
        label = ctx.day_of_week.capitalize()
        return (
            "day_of_week",
            label,
            factor,
            f"{label} carries a x{factor:.2f} weekday factor.",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_occupancy(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("occupancy", {})
        if not node.get("enabled", True):
            return None
        if ctx.occupancy is None:
            return ("occupancy", "Occupancy", 1.0, _MISSING_COPY["occupancy"], True)
        band = _band_for(ctx.occupancy, node.get("bands", []))
        if band is None:
            return ("occupancy", "Occupancy", 1.0, _MISSING_COPY["occupancy"], True)
        factor = float(band.get("multiplier", 1.0))
        return (
            "occupancy",
            f"{band.get('label', 'Occupancy')} ({ctx.occupancy:.0%})",
            factor,
            f"{ctx.units_sold} of {ctx.units_total} units sold ({ctx.occupancy:.0%}) falls in the "
            f"'{band.get('label')}' band.",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_booking_pace(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("recent_pickup", {})
        if not node.get("enabled", True):
            return None
        pace_index = (
            (ctx.recent_pickup / ctx.expected_pickup)
            if (ctx.recent_pickup is not None and ctx.expected_pickup)
            else None
        )
        if pace_index is None:
            return ("recent_pickup", "Booking pace", 1.0, _MISSING_COPY["recent_pickup"], True)
        band = _band_for(pace_index, node.get("bands", []))
        if band is None:
            return ("recent_pickup", "Booking pace", 1.0, _MISSING_COPY["recent_pickup"], True)
        factor = float(band.get("multiplier", 1.0))
        return (
            "recent_pickup",
            band.get("label", "Booking pace"),
            factor,
            f"Picked up {ctx.recent_pickup:.0f} unit(s) in the recent window vs "
            f"{ctx.expected_pickup:.1f} expected (pace index {pace_index:.2f}).",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_lead_time(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("lead_time", {})
        if not node.get("enabled", True):
            return None
        if ctx.days_to_arrival is None:
            return ("lead_time", "Lead time", 1.0, _MISSING_COPY["lead_time"], True)
        band = _band_for(
            float(ctx.days_to_arrival), node.get("bands", []), key="max_days", inclusive=True
        )
        if band is None:
            return ("lead_time", "Lead time", 1.0, _MISSING_COPY["lead_time"], True)
        factor = float(band.get("multiplier", 1.0))
        return (
            "lead_time",
            band.get("label", "Lead time"),
            factor,
            f"{ctx.days_to_arrival} day(s) until check-in.",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_urgency(self, ctx: PricingContext, cfg: dict):
        """Interaction rule: close to check-in AND still largely unsold."""
        node = cfg.get("lead_time", {}).get("urgency_discount", {})
        if not node.get("enabled", True):
            return None
        if ctx.days_to_arrival is None or ctx.occupancy is None:
            return None
        within = int(node.get("within_days", 7))
        below = float(node.get("occupancy_below", 0.5))
        if ctx.days_to_arrival <= within and ctx.occupancy < below:
            factor = float(node.get("multiplier", 1.0))
            return (
                "urgency_discount",
                node.get("label", "Unsold inventory close to check-in"),
                factor,
                f"Only {ctx.occupancy:.0%} sold with {ctx.days_to_arrival} day(s) to go — "
                f"discounting to stimulate demand.",
                abs(factor - 1.0) < 1e-9,
            )
        return None

    def _factor_season(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("season", {})
        if not node.get("enabled", True):
            return None
        if ctx.month is None:
            return ("season", "Season", 1.0, _MISSING_COPY["season"], True)
        multipliers = node.get("month_multipliers", {})
        factor = float(multipliers.get(str(ctx.month), 1.0))
        label = node.get("month_labels", {}).get(str(ctx.month)) or ctx.season_label or "Season"
        return (
            "season",
            label,
            factor,
            f"Stay date falls in month {ctx.month} ({label}).",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_event(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("event", {})
        if not node.get("enabled", True):
            return None
        if not ctx.is_event:
            return None
        factor = float(node.get("multiplier", 1.0))
        name = ctx.event_name or "Local event"
        return (
            "event",
            f"Event: {name}",
            factor,
            f"'{name}' is flagged on this stay date.",
            abs(factor - 1.0) < 1e-9,
        )

    def _factor_market(self, ctx: PricingContext, cfg: dict):
        node = cfg.get("market", {})
        if not node.get("enabled", True):
            return None
        min_obs = int(node.get("min_observations", 1))
        if ctx.market_price_index is None or ctx.market_observation_count < min_obs:
            reason = _MISSING_COPY["market"]
            if 0 < ctx.market_observation_count < min_obs:
                reason = (
                    f"Only {ctx.market_observation_count} market observation(s) available "
                    f"(minimum {min_obs}); no market adjustment applied."
                )
            return ("market", "Market signal", 1.0, reason, True)

        sensitivity = float(node.get("sensitivity", 0.5))
        raw = 1.0 + sensitivity * (ctx.market_price_index - 1.0)
        lo = float(node.get("min_multiplier", 0.9))
        hi = float(node.get("max_multiplier", 1.15))
        factor = min(max(raw, lo), hi)

        direction = "above" if ctx.market_price_index > 1 else "below"
        clamp_note = ""
        if abs(factor - raw) > 1e-9:
            clamp_note = f" (clamped from x{raw:.3f})"
        return (
            "market",
            "Market signal",
            factor,
            f"Reference market price {ctx.market_reference_net_rate:,.0f} {ctx.currency} is "
            f"{abs(ctx.market_price_index - 1) * 100:.0f}% {direction} the market baseline "
            f"({ctx.market_observation_count} observation(s), sensitivity {sensitivity:.2f})"
            f"{clamp_note}.",
            abs(factor - 1.0) < 1e-9,
        )

    # ---------------------------------------------------------- explanation
    def _build_explanation(
        self, ctx: PricingContext, adjustments: list[Adjustment], recommended: float
    ) -> str:
        applied = [a for a in adjustments if not a.is_neutral and a.code != "rounding"]
        # Signals the engine could not see. Surfaced in BOTH branches below --
        # a date where nothing moved is exactly where a blind spot matters most.
        blind_spots = [
            a.reason for a in adjustments if a.is_neutral and a.code in ctx.missing and a.reason
        ]
        if not applied:
            text = (
                f"No pricing signals moved this date away from its base price of "
                f"{ctx.band_base_net_rate:,.0f} {ctx.currency}. Recommendation held at "
                f"{recommended:,.0f} {ctx.currency}."
            )
            if blind_spots:
                text += " " + " ".join(blind_spots)
            return text
        parts = []
        for adj in applied:
            arrow = "increases" if adj.delta > 0 else "decreases"
            parts.append(f"{adj.label} {arrow} the price by {abs(adj.delta):,.0f}")
        text = (
            f"Starting from a base of {ctx.band_base_net_rate:,.0f} {ctx.currency}: "
            + "; ".join(parts)
            + f". Final recommendation {recommended:,.0f} {ctx.currency}."
        )
        if blind_spots:
            text += " " + " ".join(blind_spots)
        return text


register_engine("v1", PricingEngineV1)
