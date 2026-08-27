"""Blue Jay JSON -> vendor-neutral DTOs.

Pure functions, no network. This is the only place that knows Blue Jay's field
names, and it is the layer the first live response gets diffed against.

Three properties are load-bearing:

* **A reservation is a STAY; a Booking row is ONE OCCUPIED UNIT-NIGHT.**
  Blue Jay returns ``checkInTime``/``checkOutTime``/``night``; the rest of this
  system counts unit-nights (see ``routers/bookings.py``). Expansion happens
  here and nowhere else.
* **Nothing is guessed.** A status string or room-type name that is not mapped
  RAISES. The registry lesson in ``lookup.py`` applies with more force here,
  because the failure mode is pricing cancelled inventory as occupied.
* **Every disagreement is reported, not resolved.** The document contradicts
  itself in places; where it does, the discrepancy is surfaced for live
  verification rather than silently picked.
"""

from __future__ import annotations

import statistics
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

from ..base import BookingDTO, InventoryDTO, PhysicalRoomDTO, RoomTypeDTO


class VendorPayloadError(ValueError):
    """The response is not a payload we can read at all.

    Distinct from UnmappedValue: that one means "a value we do not recognise
    inside a well-formed payload", this one means "we should not be reading
    values out of this at all".
    """


class UnmappedValue(LookupError):
    """A vendor value with no mapping. Deliberately fatal.

    Substituting a default here would mean pricing on a guess about somebody
    else's data model — a cancelled booking counted as occupancy, or a whole
    room type silently priced as the wrong category.
    """

    def __init__(self, kind: str, value: str, known: Sequence[str]) -> None:
        self.kind = kind
        self.value = value
        self.known = list(known)
        options = ", ".join(repr(k) for k in known) or "none mapped yet"
        super().__init__(
            f"Unmapped Blue Jay {kind}: {value!r}. Known: {options}. "
            f"Map it in Settings -> Data before syncing, or the rows it covers "
            f"would be priced on a guess."
        )


@dataclass
class NormalisationReport:
    """What the adapter could not fully vouch for. Never silently discarded."""

    warnings: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    skipped: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "warnings": list(self.warnings),
            "discrepancies": list(self.discrepancies),
            "skipped": self.skipped,
        }


# --------------------------------------------------------------- statuses
#
# The reservation OUTPUT carries a localised Vietnamese string, while the INPUT
# filter uses integer codes (0 confirmed .. 5 canceled, -1 deleted). The
# document never maps the two and its samples show exactly ONE value.
#
# `occupies` is OUR decision, not the vendor's. VERIFIED: code 1 returns exactly
# one string, `Đang giữ phòng` ("currently holding the room"), so the earlier
# đã-đặt/giữ-chỗ split rested on a false premise and is gone.
#
# We count a hold AS occupancy: the room is being held and cannot be sold to
# anyone else, so it is genuinely not available inventory. Note this does NOT
# reproduce the occupancy report exactly — see docs/BLUEJAY_CONTRACT.md; the
# two disagree on roughly 3% of room-nights for reasons we have not resolved,
# which is why the report, not this, is the source for occupancy.
#
# Note the two orthographies of huỷ/hủy — Vietnamese accepts both.
@dataclass(frozen=True)
class StatusMeaning:
    code: int
    label: str
    occupies: bool
    #: False for every value inferred from the integer-code table rather than
    #: seen in a payload. The probe's FIRST job is to dump every distinct status
    #: string observed, because a wrong guess here does not raise — it silently
    #: miscounts occupancy.
    observed: bool = False


STATUS_VOCABULARY: dict[str, StatusMeaning] = {
    # VERIFIED 2026-08-27 by filtering on each documented integer code and
    # reading back the string the API returns. `đã đặt` and `giữ chỗ` were both
    # guesses and both WRONG: code 1 returns exactly ONE string.
    "đã xác nhận": StatusMeaning(0, "confirmed", True, observed=True),
    "đang giữ phòng": StatusMeaning(1, "held", True, observed=True),
    "không đến": StatusMeaning(2, "no_show", False, observed=True),
    "đã nhận phòng": StatusMeaning(3, "checked_in", True, observed=True),
    "đã trả phòng": StatusMeaning(4, "checked_out", True, observed=True),
    "đã huỷ": StatusMeaning(5, "cancelled", False, observed=True),
    "đã hủy": StatusMeaning(5, "cancelled", False, observed=True),  # spelling variant
    # Code -1 returned NO rows over an eight-month window, so deleted
    # reservations appear to be withheld entirely rather than labelled. Kept
    # provisional: never observed, and absence is not proof.
    "đã xoá": StatusMeaning(-1, "deleted", False),
    "đã xóa": StatusMeaning(-1, "deleted", False),
}

#: How many rows sharing one unrecognised status turn a record anomaly into a
#: vocabulary gap. One odd record must not cost the other 99% of a sync; the
#: SAME unknown value repeating means our vocabulary is wrong, which must be
#: loud. Same lever `generate_recommendations` uses to tell the two apart.
UNKNOWN_STATUS_FAIL_THRESHOLD = 3

#: Folded once at import so every lookup is NFC-safe.
_STATUS_LOOKUP: dict[str, "StatusMeaning"] = {}


_STATUS_LOOKUP.update(
    {unicodedata.normalize("NFC", k).strip().lower(): v for k, v in STATUS_VOCABULARY.items()}
)


def _fold(text: str | None) -> str:
    """Case-, whitespace- and Unicode-normalised key for a vendor string.

    NFC matters as much as case here: the composed and decomposed forms of the
    same Vietnamese text are visually identical and byte-different, so a
    mapping pasted from a macOS-originated source would raise UnmappedValue
    naming a room type the operator has already mapped. The huỷ/hủy spellings
    are a different problem, handled by listing both.
    """
    return unicodedata.normalize("NFC", str(text or "")).strip().lower()


def status_meaning(raw: str | None) -> StatusMeaning | None:
    """The meaning of a status string, or None when it is not in our vocabulary."""
    return _STATUS_LOOKUP.get(_fold(raw))


def provisional_status_strings() -> list[str]:
    """Values we INFERRED rather than observed — the probe's verification list."""
    return sorted(k for k, v in STATUS_VOCABULARY.items() if not v.observed)


# ------------------------------------------------------------------ dates
# ------------------------------------------------------------ coercion
# Vendor JSON is not config: it arrives untrusted, and a field may be absent,
# null, blank or a numeric string. These coerce defensively so a single odd row
# degrades instead of taking the whole sync down.
#
# They also keep this module clear of the `int(x.get(...))` shape that
# `test_every_cast_site_lives_behind_the_boundary` forbids. That guard is about
# PRICING CONFIG, which must only be cast at its boundary, so the right answer
# was to stop writing the shape rather than to exempt this file from the guard.
def _as_int(
    value: Any,
    default: int = 0,
    *,
    report: "NormalisationReport | None" = None,
    what: str = "",
) -> int:
    """Coerce, and LEAVE A TRACE when coercion falls back.

    Degrading quietly is how a malformed `night` produced an empty report while
    the module header promised every disagreement is reported. A missing value
    is normal and says nothing; a PRESENT but unreadable one is a finding.
    """
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        if report is not None:
            report.warnings.append(f"Unreadable {what or 'number'}: {value!r}; used {default}.")
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    """Blue Jay mixes `2026-05-21` and `2026-05-18 00:00:00` in the same payload."""
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # None, not a raise. Numbers already degrade here (`_as_int`), and dates
    # got the opposite treatment: one malformed value took the ENTIRE sync down,
    # including every well-formed row beside it. The format most likely to
    # appear -- dd/mm/yyyy -- is one this same vendor already uses on the
    # occupancy endpoint, so this is a realistic drift, not a hypothetical.
    return None


def parse_report_date(value: str) -> date:
    """The occupancy report uses `01/06/2026` — DAY first.

    Reading it month-first is silent and catastrophic: it shifts an entire
    report by months and every date still parses for the first twelve days.
    """
    return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()


# ------------------------------------------------------------- key lookup
def _first(row: Mapping[str, Any], *candidates: str, default: Any = None) -> Any:
    """The filter endpoints have NO documented response schema.

    Their field names are inferred from the query parameters, so the parser
    accepts several plausible spellings rather than failing on capitalisation.
    Whichever key was actually present is what live verification pins down.
    """
    lowered = {str(k).lower(): v for k, v in row.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return default


#: Envelope `status` values that mean the call succeeded. Anything else is an
#: error the caller must not read as data.
_SUCCESS_STATUSES = frozenset({"success", "ok", "true", "1"})


def _check_envelope(payload: Mapping[str, Any]) -> None:
    """Reject an error response before anything tries to read rows out of it.

    THE most dangerous failure in this adapter, because zero rows is not a
    neutral answer here: it means 0% occupancy across the whole horizon, which
    is the strongest DISCOUNT signal the pricing engine has. A revoked key, a
    quota refusal, a call that slipped outside a testing window, or a shape
    change would otherwise all render as "price everything down as far as the
    bounds allow" -- and the sync would report success.
    """
    if not isinstance(payload, Mapping):
        raise VendorPayloadError(f"Expected a JSON object, got {type(payload).__name__}.")

    # OBSERVED 2026-08-27: a THIRD envelope the document never mentions.
    # `{"errors": {"code": ..., "title": ...}}` — and it arrives with HTTP 200,
    # so neither the status-code check nor the `status` check saw it. It sailed
    # through, sanitised to `{"data": null}`, and the capture recorded no error
    # while writing a snapshot marked sanitised. D33, third instance, found by
    # real data rather than by reasoning about it.
    errors = payload.get("errors")
    if errors:  # empty list/dict alongside real data is a normal idiom
        detail = errors
        if isinstance(errors, Mapping):
            # Two grammars, observed on the same host: `code`/`title` from the
            # AUTH GATE (missing or bad apikey) and `status`/`message` from the
            # APPLICATION (unknown hotelId, closed window, date range too wide).
            # `message` carries the only real diagnosis, and it is in
            # Vietnamese — reading only `title` would reduce "the gap between
            # from and to must not exceed 1 month" to "Unauthorized" and send
            # the reader to check their API key.
            detail = (
                errors.get("message")
                or errors.get("title")
                or errors.get("code")
                or errors.get("status")
                or errors
            )
            extra = errors.get("detail")
            if extra:
                detail = f"{detail}: {extra}"
        raise VendorPayloadError(f"Blue Jay returned an error envelope: {detail}")

    status = payload.get("status")
    if status is not None and str(status).strip().lower() not in _SUCCESS_STATUSES:
        raise VendorPayloadError(
            f"Blue Jay returned status={status!r}: {payload.get('message') or 'no message'}"
        )


def _reservation_rows(payload: Mapping[str, Any]) -> list[dict]:
    """Rows from a reservation response, or a raise. NEVER a silent empty list."""
    _check_envelope(payload)
    if "data" not in payload:
        raise VendorPayloadError(
            "Reservation response has no 'data' key. An empty period must arrive as an "
            "empty reservations list, not as a missing container -- the two mean "
            "completely different things to the pricing engine."
        )
    data = payload["data"]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, Mapping):
        raise VendorPayloadError(f"Reservation 'data' is a {type(data).__name__}, not an object.")
    attributes = data.get("attributes")
    if not isinstance(attributes, Mapping) or "reservations" not in attributes:
        raise VendorPayloadError(
            "Reservation response is missing data.attributes.reservations. This is a "
            "contract change, not an empty result."
        )
    rows = attributes["reservations"]
    if not isinstance(rows, list):
        raise VendorPayloadError(f"'reservations' is a {type(rows).__name__}, not a list.")
    return [r for r in rows if isinstance(r, dict)]


def reservation_rows(payload: Mapping[str, Any]) -> list[dict]:
    """Public accessor: the raw reservation rows, validated. Callers that need
    to know how many rows a PAGE held (to detect the end of pagination) use
    this rather than counting expanded unit-nights, which is a different number.
    """
    return _reservation_rows(payload)


def occupancy_to_units(
    payload: Mapping[str, Any],
    *,
    category_map: Mapping[str, str],
    report: NormalisationReport | None = None,
) -> tuple[dict[tuple[str, date], int], dict[str, int]]:
    """`report-room-occupancy` -> (units_sold by (category, date), units_total).

    This is the OCCUPANCY SOURCE. The reservation list disagrees with it on
    roughly 3% of room-nights for reasons we could not determine, so the PMS's
    own answer wins and reservations supply only bookDate, pickup and rate.

    Field names are the VERIFIED ones, which differ from the document:
    `EmptyRoom` not `RoomEmpty`. Dates are `dd/MM/yyyy`.
    """
    report = report if report is not None else NormalisationReport()
    _check_envelope(payload)
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise VendorPayloadError(f"Occupancy 'data' is a {type(data).__name__}, not an object.")
    grand = data.get("GrandTotal")
    if not isinstance(grand, Mapping):
        raise VendorPayloadError("Occupancy response has no GrandTotal object.")

    sold: dict[tuple[str, date], int] = defaultdict(int)
    totals: dict[tuple[str, date], int] = defaultdict(int)
    for room_type in grand.get("RoomTypes") or []:
        name = str(room_type.get("RoomTypeName") or "").strip()
        try:
            category = resolve_category(name, category_map)
        except UnmappedValue:
            # Loud, but not fatal here: an unmapped type contributes no
            # occupancy rather than being folded into someone else's.
            report.warnings.append(
                f"Occupancy report contains room type {name!r}, which is not mapped to a "
                f"pricing category. Its rooms are excluded from occupancy."
            )
            continue
        for row in room_type.get("DailyDetails") or []:
            try:
                stay = parse_report_date(row.get("Date"))
            except (ValueError, TypeError):
                report.warnings.append(f"Unreadable occupancy date {row.get('Date')!r}; skipped.")
                continue
            problem = occupancy_row_problem(row)
            if problem:
                report.warnings.append(
                    f"Occupancy row for {name!r} on {stay} is {problem}: {row}. Skipped."
                )
                continue
            sold[(category, stay)] += _as_int(row.get("RoomOccupied"))
            # Blocked rooms are NOT sellable, so they leave the denominator.
            # Counting them as available understates occupancy and pushes the
            # price DOWN on a date that is actually fuller than it looks.
            totals[(category, stay)] += _as_int(row.get("TotalRoom")) - _as_int(row.get("Blocked"))

    # units_total is per category; take the max across dates so a single day
    # with a blocked room does not shrink the whole horizon.
    per_category: dict[str, int] = defaultdict(int)
    for (category, _stay), value in totals.items():
        per_category[category] = max(per_category[category], value)
    return dict(sold), dict(per_category)


# ------------------------------------------------------- reservations
def resolve_category(name: str | None, category_map: Mapping[str, str]) -> str:
    lookup = {_fold(k): v for k, v in category_map.items()}
    key = _fold(name)
    if key not in lookup:
        raise UnmappedValue("room type", str(name or ""), sorted(category_map))
    return lookup[key]


def build_name_category_map(
    room_types: Iterable[Mapping[str, Any]], id_category_map: Mapping[str, str]
) -> dict[str, str]:
    """Resolve `roomtypeName -> our category` THROUGH the room-type id.

    The persisted map is keyed by ``roomtypeId``, not by name, because Blue Jay
    does have ids -- the reservation filter documents `roomTypes` taking id
    values -- and only the reservation OUTPUT is name-only. Display names are
    editable and demonstrably inconsistent: the doc's own two-row sample uses
    two conventions at once ("Holo Ben Thanh - 1 PN" beside "Căn hộ 3 phòng
    ngủ"). Keying on the name would let a rename in Blue Jay's UI silently
    unmap a whole category.

    So this is rebuilt from `roomtype-list` on every sync, and a renamed room
    type keeps resolving.
    """
    by_id = {str(k).strip(): v for k, v in id_category_map.items()}
    out: dict[str, str] = {}
    for row in room_types:
        type_id = str(_first(row, "roomtypeId", "roomTypeId", "id", default="") or "").strip()
        name = str(_first(row, "roomtypeName", "roomTypeName", "name", default="") or "").strip()
        if name and type_id in by_id:
            out[name] = by_id[type_id]
    return out


def unmapped_room_type_ids(
    room_types: Iterable[Mapping[str, Any]], id_category_map: Mapping[str, str]
) -> list[tuple[str, str]]:
    """`(roomtypeId, roomtypeName)` pairs the operator still has to map."""
    known = {str(k).strip() for k in id_category_map}
    out: list[tuple[str, str]] = []
    for row in room_types:
        type_id = str(_first(row, "roomtypeId", "roomTypeId", "id", default="") or "").strip()
        name = str(_first(row, "roomtypeName", "roomTypeName", "name", default="") or "").strip()
        if type_id and type_id not in known:
            out.append((type_id, name))
    return out


def reservations_to_bookings(
    payload: Mapping[str, Any],
    *,
    category_map: Mapping[str, str],
    source_commission: Mapping[str, float] | None = None,
    report: NormalisationReport | None = None,
) -> list[BookingDTO]:
    """Expand each reservation into one row per occupied unit-night.

    ``checkOutTime`` is the DEPARTURE day and is not an occupied night: the
    guest sleeps from check-in night through the night before checkout.

    Failure policy differs by KIND, deliberately:

    * an unmapped ROOM TYPE raises immediately -- it is systemic by
      construction, since every row of that type is equally unmapped and a
      whole category would go unpriced;
    * an unknown STATUS skips its row and is reported, until the SAME unknown
      value repeats, which means our vocabulary is wrong rather than one record
      being odd;
    * a malformed DATE skips its row and is reported.
    """
    report = report if report is not None else NormalisationReport()
    out: list[BookingDTO] = []
    unknown_statuses: dict[str, int] = defaultdict(int)

    for index, row in enumerate(_reservation_rows(payload)):
        raw_status = str(row.get("status") or "").strip()
        meaning = status_meaning(raw_status)
        if meaning is None:
            unknown_statuses[raw_status.lower()] += 1
            if unknown_statuses[raw_status.lower()] >= UNKNOWN_STATUS_FAIL_THRESHOLD:
                raise UnmappedValue("reservation status", raw_status, sorted(STATUS_VOCABULARY))
            report.skipped += 1
            report.warnings.append(
                f"Unrecognised reservation status {raw_status!r} on booking "
                f"{row.get('bookingCode')!r}; row skipped rather than assumed occupied."
            )
            continue
        if not meaning.occupies:
            report.skipped += 1
            continue

        category = resolve_category(row.get("roomType"), category_map)

        check_in = _parse_date(row.get("checkInTime"))
        if check_in is None:
            report.warnings.append(
                f"Reservation {row.get('bookingCode')!r} has an absent or unparseable "
                f"check-in date ({row.get('checkInTime')!r}); row skipped."
            )
            report.skipped += 1
            continue

        check_out = _parse_date(row.get("checkOutTime"))
        stated = _as_int(row.get("night"), report=report, what="night count")

        if check_out is not None:
            nights = (check_out - check_in).days
            # Dates win: a range is checkable, a count is not. The disagreement
            # is reported rather than resolved, and the row is still placed --
            # skipping it would discard occupancy we can locate correctly.
            if stated and stated != nights:
                report.discrepancies.append(
                    f"Reservation {row.get('bookingCode')!r}: night={stated} but "
                    f"{check_in}..{check_out} spans {nights} night(s). Dates used."
                )
        else:
            nights = stated
            report.warnings.append(
                f"Reservation {row.get('bookingCode')!r} has no usable checkOutTime; "
                f"fell back to night={stated}."
            )

        if nights <= 0:
            report.warnings.append(
                f"Reservation {row.get('bookingCode')!r} covers no nights and was skipped."
            )
            report.skipped += 1
            continue

        # VERIFIED 2026-08-27: roomPrice is the STAY TOTAL (1 night = 500,000,
        # 3 nights = 1,500,000, 4 nights = 2,000,000 at one nightly rate), and
        # it is a GROSS, guest-facing amount -- `balance == totalPrice -
        # payment` on 122/122 real rows, so `balance` is a guest ledger and
        # `totalPrice` is what the GUEST OWES, not the hotel's receipt.
        #
        # This product prices in NET (V2), so a commissioned channel must have
        # its commission removed. `commiission` (sic) lives on the SOURCE and
        # comes from /source-list.
        # Both documented samples are `night: 1`, where those are the same
        # number, so the document contains zero evidence either way. If it is
        # in fact nightly, every multi-night date understates current_net_rate
        # by roughly the mean stay length -- which does not misprice (the band
        # anchors that) but does drive change_pct, i.e. the calendar's change
        # column and the bigChange attention threshold.
        gross_per_night = _as_float(row.get("roomPrice")) / nights
        channel = str(row.get("source") or "unknown").strip()
        commission = None
        if source_commission is not None:
            commission = source_commission.get(_fold(channel))
            if commission is None:
                # Defaulting to 0% silently overstates NET for every
                # commissioned channel, which overstates the achieved rate and
                # biases recommendations UP.
                report.warnings.append(
                    f"No commission known for source {channel!r}; treated the gross "
                    f"price as NET. If that channel charges commission, its achieved "
                    f"rate is OVERSTATED."
                )
        per_night = round(gross_per_night * (1 - (commission or 0.0) / 100.0), 2)
        # A blank code would make two different reservations on the same night
        # share an id; the row index keeps them distinguishable.
        booking_code = str(row.get("bookingCode") or "").strip() or f"ROW{index}"
        unit_label = str(row.get("roomName") or "").strip() or None
        # OBSERVED: "Unassigned" is a placeholder meaning no room has been
        # chosen yet, not a room called Unassigned. 29 of 100 real rows had it.
        if unit_label and unit_label.lower() == "unassigned":
            unit_label = None

        for offset in range(nights):
            stay = date.fromordinal(check_in.toordinal() + offset)
            out.append(
                BookingDTO(
                    # One row per night, so the id must vary per night or the
                    # whole stay collapses into whichever row is written last.
                    # bookingCode + unit + night is NOT unique: one booking can
                    # carry several UNASSIGNED rows for the same night (observed
                    # up to five). The row index is what keeps them distinct;
                    # without it they overwrite each other, which understates
                    # occupancy and pushes the price DOWN.
                    external_id=f"{booking_code}:{index}:{unit_label or '-'}:{stay.isoformat()}",
                    room_type_external_id=category,
                    stay_date=stay,
                    booked_at=_parse_date(row.get("bookDate")) or stay,
                    # ALWAYS 1. This row IS one night; Blue Jay's `night` is the
                    # stay length and putting it here would multiply occupancy
                    # by it downstream.
                    nights=1,
                    guests=0,  # not present in the reservation payload
                    net_rate=per_night,
                    channel=channel,
                    status=meaning.label,
                    physical_room_external_id=unit_label,
                )
            )

    return out


# ------------------------------------------------------ derived signals
def filter_looks_ignored(*, rows: Sequence[Any], unfiltered_total: int) -> bool:
    """Did a `roomtypeId` filter actually take effect?

    OBSERVED 2026-08-27: `roomdetail-list?roomtypeId=abc` returns EVERY room
    with `status: "Success"`. A malformed or unknown filter is IGNORED rather
    than rejected, so the caller receives the whole hotel and no error.

    Attributing all of it to one room type inflates units_total, which
    understates occupancy, which understates pace, and pushes the price DOWN
    across every date for that category. Equality with the unfiltered count is
    not proof of a problem — a hotel with one room type would match legitimately
    — so this reports SUSPICION, and the caller decides.
    """
    return unfiltered_total > 1 and len(rows) == unfiltered_total


def units_sold_by_date(bookings: Iterable[BookingDTO]) -> dict[tuple[str, date], int]:
    """On-the-books units per category per night, counted from unit-nights."""
    counts: dict[tuple[str, date], int] = defaultdict(int)
    for b in bookings:
        counts[(b.room_type_external_id, b.stay_date)] += 1
    return dict(counts)


def derive_adr(bookings: Iterable[BookingDTO]) -> dict[tuple[str, date], float]:
    """Mean nightly rate actually booked, per category per night.

    This is a REALIZED average, not a published rate — Blue Jay exposes no
    forward-looking rate at all. A date with no bookings yields no entry, which
    is precisely the far-out empty dates pricing most wants to move; callers
    must fall back explicitly rather than read a missing key as zero.
    """
    grouped: dict[tuple[str, date], list[float]] = defaultdict(list)
    for b in bookings:
        if b.net_rate > 0:
            grouped[(b.room_type_external_id, b.stay_date)].append(b.net_rate)
    return {k: round(statistics.mean(v), 2) for k, v in grouped.items() if v}


def build_inventory(
    *,
    stay_dates: Sequence[date],
    categories: Sequence[str],
    units_total: Mapping[str, int],
    units_sold: Mapping[tuple[str, date], int],
    adr: Mapping[tuple[str, date], float],
    fallback_rate: Mapping[tuple[str, date], float],
    last_known_adr: Mapping[str, float] | None = None,
) -> list[InventoryDTO]:
    """Assemble per-date inventory, recording WHICH rate source was used.

    The fallback chain is derived ADR -> last known ADR for that category ->
    the seasonal BASE FOR THAT DATE -> unavailable. Provenance travels with the row because an
    achieved average standing in for a list price must never be read as one.

    NOTE: ``last_known_adr`` is currently passed by NO caller, so the chain is
    effectively two rungs plus the unavailable state. It is kept because the
    rung it fills is real — a category with bookings SOMEWHERE in the window but
    none on a given night is better described by that category's recent
    achieved rate than by a seasonal base — and populating it needs a decision
    about the lookback window that should wait for live data rather than be
    guessed now. It is not dead code; it is an unwired seam, and this note is
    here so the next reader does not mistake one for the other.
    """
    last_known_adr = last_known_adr or {}
    rows: list[InventoryDTO] = []
    for category in categories:
        for stay in stay_dates:
            rate = adr.get((category, stay))
            provenance = "derived_adr"
            if rate is None:
                rate = last_known_adr.get(category)
                provenance = "last_known_adr"
            if rate is None:
                # Keyed by (category, DATE), like `adr`. A per-category rate
                # looked up once at the window start stretched ONE season's band
                # across the whole horizon — measured at +9.5% on Low Season 2
                # dates and -8% on High Season 2 dates from an August start.
                # D17 says the season SELECTS the band; this is the same
                # double-count arriving from the other direction.
                rate = fallback_rate.get((category, stay))
                provenance = "seasonal_base"
            if rate is None:
                # The FOURTH outcome. Three named sources produced nothing, and
                # labelling that `seasonal_base` would claim a seasonal base
                # supplied a rate when none did -- the `has_band` shape again.
                # It is quiet downstream too: change_pct guards its zero
                # denominator and returns 0.0, so the row would render as a
                # confident "no change" rather than "no rate known".
                rate = 0.0
                provenance = "unavailable"
            rows.append(
                InventoryDTO(
                    room_type_external_id=category,
                    stay_date=stay,
                    units_total=_as_int(units_total.get(category)),
                    units_sold=_as_int(units_sold.get((category, stay))),
                    current_net_rate=_as_float(rate),
                    rate_provenance=provenance,
                )
            )
    return rows


# ------------------------------------------------------ room types / units
def room_types_to_dtos(
    room_types: Iterable[Mapping[str, Any]],
    rooms_by_type: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    category_map: Mapping[str, str],
    property_external_id: str,
    fallback_rates: Mapping[str, float] | None = None,
    unfiltered_room_total: int | None = None,
    report: NormalisationReport | None = None,
) -> list[RoomTypeDTO]:
    """Collapse Blue Jay room types onto OUR three categories.

    ``rooms_by_type`` maps roomtypeId -> the rows from
    ``roomdetail-list?roomtypeId=``, i.e. ONE CALL PER ROOM TYPE. That is not a
    convenience: a real roomdetail row is ``{id, roomName}`` with no
    roomtypeId, so an unfiltered list cannot be grouped at all — an earlier
    version tried and produced zero units for every category.

    ``external_id`` is the category rather than Blue Jay's roomtypeId because
    the reservation payload references room types by localised NAME only. Two
    Blue Jay types mapping to one category correctly sum their units.

    Counting rooms per type is the ASSUMPTIONS U11 unblock, verified live: 15
    types, 67 rooms, per-type counts summing exactly to the unfiltered list.
    """
    report = report if report is not None else NormalisationReport()
    fallback_rates = fallback_rates or {}

    units: dict[str, int] = defaultdict(int)
    capacity: dict[str, int] = {}
    for row in room_types:
        name = str(_first(row, "roomtypeName", "roomTypeName", "name", default="") or "").strip()
        type_id = str(_first(row, "roomtypeId", "roomTypeId", "id", default="") or "").strip()
        category = resolve_category(name, category_map)
        rooms = list(rooms_by_type.get(type_id) or [])

        if unfiltered_room_total is not None and filter_looks_ignored(
            rows=rooms, unfiltered_total=unfiltered_room_total
        ):
            # The response matched the WHOLE hotel, which is what a rejected
            # filter returns. Counting it would hand this category every room.
            report.warnings.append(
                f"Room type {name!r} (id {type_id!r}) returned {len(rooms)} rooms, the same "
                f"as the unfiltered list — the roomtypeId filter was probably IGNORED. "
                f"Counted as 0 rather than assigning the whole property to one type."
            )
            rooms = []
        elif not rooms:
            report.warnings.append(
                f"Room type {name!r} (id {type_id!r}) has no physical rooms. Occupancy is "
                f"units_sold/units_total, so a zero here makes every pace signal for it "
                f"undefined."
            )

        units[category] += len(rooms)
        capacity.setdefault(category, _as_int(_first(row, "capacity", "occ_max", "maxPerson"), 4))

    return [
        RoomTypeDTO(
            external_id=category,
            property_external_id=property_external_id,
            name=category,
            category=category,
            capacity=_as_int(capacity.get(category), 4),
            units_total=total,
            fallback_base_net_rate=_as_float(fallback_rates.get(category)),
        )
        for category, total in sorted(units.items())
    ]


def physical_rooms_to_dtos(
    physical_rooms: Iterable[Mapping[str, Any]],
    room_types: Iterable[Mapping[str, Any]],
    *,
    category_map: Mapping[str, str],
) -> list[PhysicalRoomDTO]:
    """The 22 individual apartments, keyed to the category they belong to."""
    category_by_type_id: dict[str, str] = {}
    for row in room_types:
        name = str(_first(row, "roomtypeName", "roomTypeName", "name", default="") or "").strip()
        type_id = str(_first(row, "roomtypeId", "roomTypeId", "id", default="") or "")
        category_by_type_id[type_id] = resolve_category(name, category_map)

    out: list[PhysicalRoomDTO] = []
    for room in physical_rooms:
        type_id = str(_first(room, "roomtypeId", "roomTypeId", default="") or "")
        category = category_by_type_id.get(type_id)
        if category is None:
            continue
        label = str(_first(room, "roomName", "roomdetailName", "name", default="") or "").strip()
        out.append(
            PhysicalRoomDTO(
                external_id=str(_first(room, "roomdetailId", "roomDetailId", "id", default=label)),
                room_type_external_id=category,
                unit_label=label,
            )
        )
    return out


# ------------------------------------------------------ occupancy report
def occupancy_row_problem(daily: Mapping[str, Any]) -> str | None:
    """`"unparseable"`, `"inconsistent"`, or None when the row checks out.

    Kept distinct because they warrant different conversations with Blue Jay:
    "your arithmetic disagrees with itself" and "you sent junk in TotalRoom"
    are not the same report, and collapsing both to False loses that.
    """
    # `EmptyRoom` is what the API actually sends; `RoomEmpty` is what the
    # document says. Reading only the documented name made every REAL row
    # "unparseable", so occupancy came out as zero on perfectly good data.
    empty = _first(daily, "EmptyRoom", "RoomEmpty")
    if empty is None or "TotalRoom" not in daily or "RoomOccupied" not in daily:
        return "unparseable"
    raw = [daily["TotalRoom"], daily["RoomOccupied"], empty, daily.get("Blocked", 0)]
    for value in raw:
        if value is None or isinstance(value, bool):
            return "unparseable"
        try:
            float(value)
        except (TypeError, ValueError):
            return "unparseable"

    total = _as_int(daily["TotalRoom"])
    occupied = _as_int(daily["RoomOccupied"])
    blocked = _as_int(daily.get("Blocked"))
    empty_value = _as_int(_first(daily, "EmptyRoom", "RoomEmpty"))
    return None if total - occupied - blocked == empty_value else "inconsistent"


def occupancy_row_is_consistent(daily: Mapping[str, Any]) -> bool:
    """Does a row satisfy total - occupied - blocked == empty?

    The documented sample's GRAND TOTAL does (30849 - 781 - 36 = 30032, which
    matches), and that is positive evidence this is the vendor's intended
    invariant rather than our inference. Its room-type and daily-detail rows do
    NOT (3003 - 73 - 0 = 2930 against a stated RoomEmpty of 2970) and repeat
    identical figures at every level -- the signature of placeholder data, not
    of a broken report.

    So this endpoint is a CROSS-CHECK against occupancy derived from
    reservations, never the source of truth.
    """
    return occupancy_row_problem(daily) is None
