"""SeasonalRateBook — CLIENT-VALIDATED business fact.

=============================================================================
 SOURCE: Luminous Luxury Apartments, "Business Assumptions" (client document).
 STATUS: CLIENT_VALIDATED — this is NOT a modelling assumption.

 These MIN / BASE / MAX figures are **NET rates**: what Luminous receives,
 not the guest-facing OTA price. They already encode seasonality, which is
 exactly why the pricing engine must NOT multiply a seasonality factor on top
 (that would double-count the season). Season selects the band; it does not
 scale it.

 The client's own conclusion, translated:
   "The base-rate layer does not need modelling and does not need to be
    inferred from history. It already exists and has been validated by real
    operation. Load the rate table as a lookup table.
    What is needed is the dynamic layer on top: booking pace, lead time,
    events, competitor response."
=============================================================================
"""

from __future__ import annotations

import calendar

from dataclasses import dataclass
from datetime import date

RATE_BOOK_SOURCE = "CLIENT_VALIDATED"
# The third value `source` can take. Not a band at all: it means no band covered
# the date and the ROOM TYPE's fallback rates were substituted. The other two --
# CLIENT_VALIDATED and OPERATOR_EDITED -- are both real bands and differ only in
# provenance, which is why "is there a band?" and "is it validated?" are
# different questions and must not share a predicate.
NO_BAND_SOURCE = "FALLBACK"
RATE_BASIS = "NET"

# --- room categories -------------------------------------------------------
CATEGORY_2BR_REGULAR = "2br_regular"
CATEGORY_2BR_PREMIUM = "2br_premium"
CATEGORY_3BR = "3br"

ROOM_CATEGORIES = [
    {"key": CATEGORY_2BR_REGULAR, "label": "2BR Regular", "label_vi": "2 phòng ngủ thường", "capacity": 4},
    {"key": CATEGORY_2BR_PREMIUM, "label": "2BR Premium", "label_vi": "2 phòng ngủ premium", "capacity": 4},
    {"key": CATEGORY_3BR, "label": "3BR", "label_vi": "3 phòng ngủ", "capacity": 6},
]
CATEGORY_LABELS = {c["key"]: c["label"] for c in ROOM_CATEGORIES}

# --- seasons ---------------------------------------------------------------
# NOTE: High Season 2 wraps the year end (Nov, Dec, Jan). January belongs to
# the Nov–Jan high season, NOT to a "start of year" season. This wrap is the
# single most error-prone part of the table and is covered by tests.
SEASONS = [
    {
        "key": "low_1",
        "label": "Low Season 1 (May–Jun)",
        "months": [5, 6],
        "note": "Mostly business travel, little tourism.",
    },
    {
        "key": "high_1",
        "label": "High Season 1 (Jul–Aug)",
        "months": [7, 8],
        "note": "Summer tourism — international and family travel.",
    },
    {
        "key": "low_2",
        "label": "Low Season 2 (Sep–Oct)",
        "months": [9, 10],
        "note": "Predominantly business travel.",
    },
    {
        "key": "high_2",
        "label": "High Season 2 (Nov–Jan)",
        "months": [11, 12, 1],
        "note": "Holiday season.",
    },
    {
        "key": "medium",
        "label": "Medium Season (Feb–Apr)",
        "months": [2, 3, 4],
        "note": "",
    },
]
SEASON_LABELS = {s["key"]: s["label"] for s in SEASONS}
SEASON_MONTHS = {s["key"]: list(s["months"]) for s in SEASONS}
SEASON_NOTES = {s["key"]: s["note"] for s in SEASONS}

# month -> season_key, derived once so lookup is O(1) and cannot drift.
MONTH_TO_SEASON: dict[int, str] = {}
for _season in SEASONS:
    for _m in _season["months"]:
        MONTH_TO_SEASON[_m] = _season["key"]
assert len(MONTH_TO_SEASON) == 12, "every month must map to exactly one season"

# --- the validated table ---------------------------------------------------
# (season_key, category) -> (MIN, BASE, MAX) NET VND
CLIENT_RATE_TABLE: dict[tuple[str, str], tuple[int, int, int]] = {
    # LOW SEASON 1 — May–June
    ("low_1", CATEGORY_2BR_REGULAR): (1_800_000, 2_000_000, 2_200_000),
    ("low_1", CATEGORY_2BR_PREMIUM): (2_000_000, 2_300_000, 2_500_000),
    ("low_1", CATEGORY_3BR):         (2_700_000, 2_800_000, 3_200_000),
    # HIGH SEASON 1 — July–August
    ("high_1", CATEGORY_2BR_REGULAR): (2_100_000, 2_300_000, 2_600_000),
    ("high_1", CATEGORY_2BR_PREMIUM): (2_400_000, 2_700_000, 2_900_000),
    ("high_1", CATEGORY_3BR):         (2_900_000, 3_300_000, 3_500_000),
    # LOW SEASON 2 — September–October
    ("low_2", CATEGORY_2BR_REGULAR): (1_800_000, 2_100_000, 2_300_000),
    ("low_2", CATEGORY_2BR_PREMIUM): (2_000_000, 2_400_000, 2_700_000),
    ("low_2", CATEGORY_3BR):         (2_600_000, 2_800_000, 3_000_000),
    # HIGH SEASON 2 — November–January
    ("high_2", CATEGORY_2BR_REGULAR): (2_100_000, 2_500_000, 3_200_000),
    ("high_2", CATEGORY_2BR_PREMIUM): (2_500_000, 3_000_000, 3_500_000),
    ("high_2", CATEGORY_3BR):         (3_200_000, 3_800_000, 4_300_000),
    # MEDIUM SEASON — February–April
    ("medium", CATEGORY_2BR_REGULAR): (2_000_000, 2_300_000, 2_500_000),
    ("medium", CATEGORY_2BR_PREMIUM): (2_200_000, 2_500_000, 2_700_000),
    ("medium", CATEGORY_3BR):         (2_700_000, 3_200_000, 3_500_000),
}
assert len(CLIENT_RATE_TABLE) == len(SEASONS) * len(ROOM_CATEGORIES) == 15


@dataclass(frozen=True)
class RateBand:
    """The MIN/BASE/MAX NET rates that apply to one room category on one date."""

    season_key: str
    season_label: str
    room_category: str
    min_net_rate: float
    base_net_rate: float
    #: OPTIONAL. None means the season imposes no ceiling of its own, so the
    #: only limit is the dynamic bound in Strategy. Not unbounded -- just not
    #: bounded HERE. See ASSUMPTIONS U9.
    max_net_rate: float | None
    currency: str = "VND"
    rate_basis: str = RATE_BASIS
    source: str = RATE_BOOK_SOURCE
    note: str | None = None

    def clamp(self, value: float) -> tuple[float, str | None]:
        """Clamp a rate into the band. Returns (value, 'min'|'max'|None)."""
        if value < self.min_net_rate:
            return self.min_net_rate, "min"
        if self.max_net_rate is not None and value > self.max_net_rate:
            return self.max_net_rate, "max"
        return value, None

    def to_dict(self) -> dict:
        return {
            "season_key": self.season_key,
            "season_label": self.season_label,
            "room_category": self.room_category,
            "min_net_rate": self.min_net_rate,
            "base_net_rate": self.base_net_rate,
            "max_net_rate": self.max_net_rate,
            "currency": self.currency,
            "rate_basis": self.rate_basis,
            "source": self.source,
            "note": self.note,
        }


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def season_bounds(day: date) -> tuple[date, date]:
    """First and last day of the season containing ``day``.

    A season is a CONTIGUOUS run of whole months, and one of them wraps the
    year end -- High Season 2 is Nov-Dec-Jan. Reading the run as
    min(months)..max(months) inside a single year turns that into
    January-to-December, which would let the Rate picker span a range across
    three other seasons and write one price into bands it was never checked
    against. So the run is walked from its real start month instead, and
    January resolves to the season that began the PREVIOUS November.
    """
    return season_bounds_in(day, SEASON_MONTHS[season_for(day)])


def season_bounds_in(day: date, months: list[int]) -> tuple[date, date]:
    """As ``season_bounds``, for an EXPLICIT month run.

    Takes the run rather than looking it up so a persisted, operator-edited
    calendar gets the same wrap-aware arithmetic as the client one — the two
    must not be able to answer differently.
    """
    present = set(months)
    # The start is the month whose predecessor is NOT in the season. For a
    # wrapping run that is 11, not 1.
    start_month = next(m for m in months if (m - 2) % 12 + 1 not in present)

    # How far into the run this date sits, counting forward from the start and
    # wrapping through December.
    offset = (day.month - start_month) % 12
    start_year, start_m = _shift_month(day.year, day.month, -offset)
    end_year, end_m = _shift_month(start_year, start_m, len(months) - 1)
    return (
        date(start_year, start_m, 1),
        date(end_year, end_m, calendar.monthrange(end_year, end_m)[1]),
    )


def season_for(day: date) -> str:
    return MONTH_TO_SEASON[day.month]


def season_label_for(day: date) -> str:
    return SEASON_LABELS[season_for(day)]


class SeasonalRateBook:
    """Lookup of validated rate bands.

    Defaults to the client table; can be constructed from persisted rows so an
    operator edit in Settings takes effect without a code change.
    """

    def __init__(
        self,
        table: dict[tuple[str, str], tuple[float, float, float]] | None = None,
        *,
        seasons: list[dict] | None = None,
    ) -> None:
        self._table = dict(table) if table else dict(CLIENT_RATE_TABLE)
        # The season calendar travels WITH the book rather than being read from
        # the module global at lookup time. Once an operator can edit seasons,
        # bands-from-the-database plus mapping-from-the-constant are two
        # different answers that can silently disagree -- the band table saying
        # September is high season while the mapping still says low, and a date
        # quoted from the wrong band with nothing failing.
        self._seasons = [dict(s) for s in (seasons if seasons is not None else SEASONS)]
        self._month_to_season = {
            int(month): str(season["key"])
            for season in self._seasons
            for month in season.get("months") or []
        }
        self._labels = {str(s["key"]): str(s.get("label") or s["key"]) for s in self._seasons}
        self._notes = {str(s["key"]): (s.get("note") or None) for s in self._seasons}

    @classmethod
    def from_rows(cls, rows, seasons: list[dict] | None = None) -> "SeasonalRateBook":
        """Build from persisted bands, and from the persisted calendar if given.

        ``seasons`` defaults to the client calendar so existing callers keep
        their behaviour; the caller that owns edited seasons passes them.
        """
        return cls(
            {
                (r.season_key, r.room_category): (r.min_net_rate, r.base_net_rate, r.max_net_rate)
                for r in rows
            },
            seasons=seasons,
        )

    def season_for(self, stay_date: date) -> str | None:
        return self._month_to_season.get(stay_date.month)

    @property
    def seasons(self) -> list[dict]:
        return [dict(s) for s in self._seasons]

    def lookup(self, room_category: str, stay_date: date) -> RateBand | None:
        season_key = self.season_for(stay_date)
        if season_key is None:
            # A month no season covers. Returning None rather than guessing:
            # an unpriced date is visible, a date quoted from an arbitrary band
            # is not.
            return None
        entry = self._table.get((season_key, room_category))
        if entry is None:
            return None
        minimum, base, maximum = entry
        return RateBand(
            season_key=season_key,
            season_label=self._labels.get(season_key, season_key),
            room_category=room_category,
            min_net_rate=float(minimum),
            base_net_rate=float(base),
            # NULLABLE: an empty MAX means the only ceiling is the dynamic
            # bound in Strategy. See ASSUMPTIONS U9.
            max_net_rate=float(maximum) if maximum is not None else None,
            note=self._notes.get(season_key) or None,
        )

    def all_bands(self) -> list[dict]:
        out = []
        for season in SEASONS:
            for category in ROOM_CATEGORIES:
                entry = self._table.get((season["key"], category["key"]))
                if entry is None:
                    continue
                minimum, base, maximum = entry
                out.append(
                    {
                        "season_key": season["key"],
                        "season_label": season["label"],
                        "months": season["months"],
                        "note": season["note"],
                        "room_category": category["key"],
                        "room_category_label": category["label"],
                        "min_net_rate": float(minimum),
                        "base_net_rate": float(base),
                        "max_net_rate": float(maximum),
                        "currency": "VND",
                        "rate_basis": RATE_BASIS,
                        "source": RATE_BOOK_SOURCE,
                    }
                )
        return out
