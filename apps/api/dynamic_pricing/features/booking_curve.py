"""BookingCurveProvider — expected on-the-books occupancy by lead time.

WHY THIS EXISTS
    Occupancy alone is meaningless without the booking window. 30% sold at
    D-90 may be ahead of pace; 30% sold at D-2 is a problem. Comparing actual
    occupancy against an *expected* curve turns two ambiguous signals
    (occupancy, lead time) into one meaningful one: **pace gap**.

        expected_occupancy = BookingCurve(room_type, season, days_to_arrival)
        pace_gap           = actual_otb_occupancy - expected_occupancy

=============================================================================
 THE DEMO CURVES BELOW ARE UNVALIDATED.
 They are NOT Luminous data. Luminous' historical booking curves are not
 available yet — the client document states Blue Jay has no data retention,
 though history "can be extracted, given time".
 Replace DemoBookingCurveProvider with HistoricalBookingCurveProvider as soon
 as real pickup history exists. See ASSUMPTIONS.md (U1).
=============================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# Anchor points: days-to-arrival -> fraction of final occupancy already on the
# books. Interpolated linearly between anchors. Shape only — magnitudes are a
# placeholder for a real curve fitted to Luminous history.
# NOTE the ceiling: a 22-unit building does not expect to be 100% sold on
# arrival day. Expected OTB occupancy tops out around 82%, which is what makes
# a negative pace gap meaningful rather than universal.
DEMO_CURVE_ANCHORS: list[tuple[int, float]] = [
    (0, 0.82),
    (1, 0.80),
    (3, 0.75),
    (7, 0.67),
    (14, 0.56),
    (21, 0.48),
    (30, 0.40),
    (45, 0.28),
    (60, 0.20),
    (90, 0.11),
    (120, 0.06),
    (365, 0.02),
]

# Hard ceiling after season/category scaling. Without it, a pace multiplier
# pushes the near-in expectation to 100% and every date reads "behind pace".
MAX_EXPECTED_OCCUPANCY = 0.92

# Seasons book up at different speeds. UNVALIDATED multipliers on the curve.
DEMO_SEASON_PACE: dict[str, float] = {
    "high_1": 1.15,   # summer leisure books earlier
    "high_2": 1.20,   # holiday season books earliest
    "medium": 1.00,
    "low_1": 0.85,    # business travel books late
    "low_2": 0.85,
}

# Larger units book earlier (families plan ahead). UNVALIDATED.
DEMO_CATEGORY_PACE: dict[str, float] = {
    "2br_regular": 1.00,
    "2br_premium": 1.00,
    "3br": 1.10,
}


class BookingCurveProvider(ABC):
    """Stable contract so a historical implementation can drop straight in."""

    name: str = "abstract"
    validated: bool = False

    @abstractmethod
    def expected_occupancy(
        self, room_category: str, season_key: str | None, days_to_arrival: int
    ) -> float | None:
        """Expected on-the-books occupancy, 0..1, or None if unknown."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "validated": self.validated}


class DemoBookingCurveProvider(BookingCurveProvider):
    """Synthetic, deterministic, and explicitly UNVALIDATED."""

    name = "DemoBookingCurveProvider"
    validated = False

    def __init__(
        self,
        anchors: list[tuple[int, float]] | None = None,
        season_pace: dict[str, float] | None = None,
        category_pace: dict[str, float] | None = None,
    ) -> None:
        self.anchors = sorted(anchors or DEMO_CURVE_ANCHORS)
        self.season_pace = season_pace or DEMO_SEASON_PACE
        self.category_pace = category_pace or DEMO_CATEGORY_PACE

    def expected_occupancy(
        self, room_category: str, season_key: str | None, days_to_arrival: int
    ) -> float | None:
        if days_to_arrival is None or days_to_arrival < 0:
            return None
        base = self._interpolate(days_to_arrival)
        base *= self.season_pace.get(season_key or "", 1.0)
        base *= self.category_pace.get(room_category, 1.0)
        return round(min(max(base, 0.0), MAX_EXPECTED_OCCUPANCY), 4)

    def _interpolate(self, dta: int) -> float:
        anchors = self.anchors
        if dta <= anchors[0][0]:
            return anchors[0][1]
        if dta >= anchors[-1][0]:
            return anchors[-1][1]
        for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
            if x0 <= dta <= x1:
                if x1 == x0:
                    return y0
                ratio = (dta - x0) / (x1 - x0)
                return y0 + (y1 - y0) * ratio
        return anchors[-1][1]


class HistoricalBookingCurveProvider(BookingCurveProvider):
    """Placeholder for curves fitted to real Luminous pickup history.

    BLOCKED: requires per-booking creation timestamps and enough history to
    fit a curve per (category, season, days-to-arrival). The client document
    states Blue Jay has no data retention, but that history can be extracted
    with time. Until then this provider reports no expectation, which makes
    the pace factor go neutral rather than silently wrong.
    """

    name = "HistoricalBookingCurveProvider"
    validated = True

    def expected_occupancy(self, room_category, season_key, days_to_arrival):
        return None


def get_booking_curve_provider(config: dict | None = None) -> BookingCurveProvider:
    node = (config or {}).get("booking_curve", {}) or {}
    if node.get("provider") == "historical":
        return HistoricalBookingCurveProvider()
    return DemoBookingCurveProvider(
        anchors=[(int(a["days"]), float(a["expected"])) for a in node["anchors"]]
        if node.get("anchors")
        else None,
        season_pace=node.get("season_pace"),
        category_pace=node.get("category_pace"),
    )
