"""Strip everything a captured Blue Jay response does not need to keep.

**Allowlist, not denylist.** A denylist ships whatever field Blue Jay adds
next; this fails closed by construction, which is the only defensible default
when the payload carries guest identity documents.

What the pricing pipeline needs from a reservation is small: which room type,
which nights, when it was booked, through which channel, at what room price,
and whether it counts as occupancy. It needs no guest name, no document image,
no free-text note, and no payment position.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Mapping

#: Everything downstream consumes, and nothing else. Compare against
#: `normalize.reservations_to_bookings`, which reads exactly these.
RESERVATION_ALLOWLIST: tuple[str, ...] = (
    "bookingCode",  # pseudonymised below, never carried verbatim
    "roomType",
    "roomName",
    "source",
    "status",
    "bookDate",
    "checkInTime",
    "checkOutTime",
    "night",
    "roomPrice",
)

#: Named only so the docs and tests can point at what is deliberately dropped.
#: The pipeline does not consult this list — dropping is the default.
KNOWN_SENSITIVE_FIELDS: tuple[str, ...] = (
    "guestName",
    "guestImagepaper",
    "note",
    "referenceCode",
    "payment",
    "balance",
    "deposit",
    "servicePrice",
    "totalPrice",
    "arrivalTime",
    "departureTime",
)

#: Salt for booking-code pseudonyms, read from the environment.
#:
#: It must be STABLE (a per-run random salt would make two captures of the same
#: reservation look like different bookings, breaking the comparisons snapshots
#: exist for) but it must NOT be the in-source default, because this repo is
#: public and Blue Jay's booking codes are 6-digit numerics: a million-entry
#: rainbow table against a known salt is built in under a second, so the
#: fallback below buys no unlinkability at all.
#:
#: Set BLUEJAY_PSEUDONYM_SALT on any machine that captures real data. The
#: default exists only so CI fixture tests stay deterministic, and it is
#: deliberately named to say so.
_SALT_ENV_VAR = "BLUEJAY_PSEUDONYM_SALT"
_PUBLIC_FIXTURE_SALT = b"dpp/public-fixtures-only"


def _salt() -> bytes:
    # blake2s caps its key at 32 bytes.
    supplied = os.getenv(_SALT_ENV_VAR, "").strip()
    return supplied.encode("utf-8")[:32] if supplied else _PUBLIC_FIXTURE_SALT


def salt_is_private() -> bool:
    """False when captures would be pseudonymised with the PUBLIC default.

    Surfaced by the capture tooling so nobody sanitises real data believing the
    booking codes are protected when they are trivially recoverable.
    """
    return bool(os.getenv(_SALT_ENV_VAR, "").strip())


def pseudonymise(value: str) -> str:
    """Stable, non-reversible stand-in for a booking code."""
    digest = hashlib.blake2s(str(value).encode("utf-8"), key=_salt(), digest_size=5)
    return f"BJ-{digest.hexdigest().upper()}"


def sanitize_reservation_row(row: Mapping[str, Any]) -> dict[str, Any]:
    clean = {key: row[key] for key in RESERVATION_ALLOWLIST if key in row}
    if "bookingCode" in clean:
        clean["bookingCode"] = pseudonymise(clean["bookingCode"])
    return clean


def sanitize_reservations(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitise a reservation response, preserving its envelope shape.

    The envelope is kept so a snapshot replays through exactly the same parser
    as a live response — a snapshot that needed its own parser would stop
    being evidence about the live one.
    """
    # The ENVELOPE survives. `status`/`message` carry no personal data --
    # `message` is vendor prose about the REQUEST -- and dropping them turned an
    # error response into a structurally valid snapshot asserting 0% occupancy
    # on every date. A snapshot recording "this capture failed" is far more
    # useful than one that silently reads as an empty hotel, every time it
    # replays. `_check_envelope` can only protect the snapshot path if the
    # thing it checks still exists.
    #
    # `message` is carried VERBATIM, which is a small residual risk worth
    # naming: the reservation endpoint accepts a `search` parameter that can be
    # a guest name, and a vendor error echoing the search term back would carry
    # it here. We never send `search` — `plan_requests` does not include it —
    # so nothing we ask for can put a guest name in a message today. If that
    # ever changes, this is the line that has to change with it.
    envelope = {k: payload[k] for k in ("status", "message") if k in payload}

    data = payload.get("data")
    if data is None:
        # Preserved as None rather than coerced to {}: "there was no data" and
        # "there were no reservations" are different facts, and the coercion
        # was what made the two indistinguishable downstream.
        return {**envelope, "data": None}
    if isinstance(data, list):
        rows = [sanitize_reservation_row(r) for r in data if isinstance(r, dict)]
        return {**envelope, "meta": dict(payload.get("meta") or {}), "data": rows}

    if not isinstance(data, dict):
        return {**envelope, "data": data if isinstance(data, (str, int, float, bool)) else None}
    attributes = data.get("attributes") or {}
    rows = [
        sanitize_reservation_row(r)
        for r in (attributes.get("reservations") or [])
        if isinstance(r, dict)
    ]
    out: dict[str, Any] = {
        **envelope,
        "data": {"type": data.get("type", "reservation"), "attributes": {"reservations": rows}},
    }
    if payload.get("meta"):
        out["meta"] = dict(payload["meta"])
    return out


#: The filter endpoints carry no personal data — room types, physical rooms and
#: booking sources are property configuration. They are still passed through an
#: allowlist so an unexpected field cannot ride along into a snapshot.
ROOM_TYPE_ALLOWLIST = ("roomtypeId", "roomTypeId", "id", "roomtypeName", "roomTypeName", "name", "capacity", "maxPerson")
ROOM_DETAIL_ALLOWLIST = (
    "roomdetailId", "roomDetailId", "id", "roomName", "roomdetailName", "name",
    # Every spelling normalize._first accepts must be here, or the live path
    # parses and the snapshot does not. Case folding does not fold underscores.
    "roomtypeId", "roomTypeId", "roomtype_id", "floor",
)
SOURCE_ALLOWLIST = ("sourceId", "id", "sourceName", "name", "categorySource")


def sanitize_rows(rows: Any, allowlist: tuple[str, ...]) -> list[dict[str, Any]]:
    """Keep allowlisted keys, matching CASE-INSENSITIVELY.

    `normalize._first` accepts several spellings of the same undocumented
    field, so a case-sensitive filter here would let a snapshot parse
    differently from the live response it was captured from -- breaking the
    invariant that a snapshot replays through exactly the same parser. The
    worst case is silent: an all-lowercase row sanitises to {}, every physical
    room collapses under an empty key, and units_total goes to zero.
    """
    if not isinstance(rows, list):
        return []
    wanted = {k.lower() for k in allowlist}
    return [
        {k: v for k, v in row.items() if str(k).lower() in wanted}
        for row in rows
        if isinstance(row, dict)
    ]
