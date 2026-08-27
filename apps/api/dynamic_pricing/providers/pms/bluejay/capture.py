"""One-pass capture of Blue Jay's responses, and the snapshot it produces.

The testing window is short and shared, so a capture has to be right the first
time. That shapes everything here:

* the request PLAN is built without touching the network, so it can be reviewed
  and dry-run for free;
* every response is written RAW, because raw is how we learn what live actually
  returns versus what the document claims;
* a SANITIZED copy is produced separately, and it is the only one meant to
  leave the machine;
* the things we most need to verify — the real status vocabulary, unmapped room
  types — are reported as findings rather than buried in the files.

Raw output contains guest names and identity-document references. Both output
directories are gitignored, and this repository is public.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import normalize, sanitize, windows
from .client import BlueJayClient

RAW_DIRNAME = "raw"
SNAPSHOT_DIRNAME = "snapshot"


@dataclass(frozen=True)
class RequestStep:
    """One planned GET. Built without a client so a dry run costs nothing."""

    name: str
    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)
    #: Which allowlist sanitises the response; None means the reservation
    #: envelope sanitiser, which is the only one carrying personal data.
    allowlist: tuple[str, ...] | None = None


@dataclass
class CaptureResult:
    raw_dir: Path
    snapshot_dir: Path
    observed_statuses: list[str] = field(default_factory=list)
    unmapped_room_types: list[tuple[str, str]] = field(default_factory=list)
    #: Room-type names as they appear in RESERVATIONS versus in the FILTER
    #: endpoint. Reservations join by name, and nothing guarantees the two use
    #: the same vocabulary — dumping both answers on the first run what would
    #: otherwise stay a guess until a sync failed.
    reservation_room_type_names: list[str] = field(default_factory=list)
    filter_room_type_names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def plan_requests(start: date, end: date) -> list[RequestStep]:
    """Every request the adapter depends on, in the order to make them.

    VERIFIED against api1.bluejaypms.com on 2026-08-27. Filters first: they are
    small, they are NOT window-restricted (they answered 22 minutes after the
    window closed), and `roomtype-list` is what everything else is interpreted
    through.

    `report-room-occupancy` is chunked because the API rejects a range wider
    than one month — a constraint the document does not mention.

    `extraservice-sumary` is deliberately ABSENT. Pricing does not use it, and
    the cheapest way to protect data is not to fetch it.
    """
    steps: list[RequestStep] = [
        RequestStep("roomtype-list", "roomtype-list", {}, sanitize.ROOM_TYPE_ALLOWLIST),
        RequestStep("roomdetail-list", "roomdetail-list", {}, sanitize.ROOM_DETAIL_ALLOWLIST),
        RequestStep("source-list", "source-list", {}, sanitize.SOURCE_ALLOWLIST),
        RequestStep("source-category", "source-category", {}, sanitize.SOURCE_ALLOWLIST),
    ]
    # Occupancy: one call per <=27-day chunk.
    for chunk_start, chunk_end in _month_chunks(start, end):
        steps.append(
            RequestStep(
                f"report-room-occupancy-{chunk_start.isoformat()}",
                "report-room-occupancy",
                {"dateType": 1, "from": chunk_start.isoformat(), "to": chunk_end.isoformat()},
            )
        )
    # Reservations LAST and paged: `meta.total` is capped at `limit`, so a
    # short page is the only end marker.
    steps.append(
        RequestStep(
            "reservation",
            "reservation",
            {
                # dateType=3 is STAY NIGHT: bookings, occupancy and a derived
                # rate from one endpoint.
                "dateType": 3,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "limit": 500,
                "page": 1,
            },
        )
    )
    return steps


def _month_chunks(start: date, end: date, size: int = 27) -> list[tuple[date, date]]:
    """VERIFIED: report-room-occupancy rejects a range wider than one month."""
    out: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(date.fromordinal(cursor.toordinal() + size), end)
        out.append((cursor, stop))
        cursor = date.fromordinal(stop.toordinal() + 1)
    return out


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _distinct(payload: Any, key: str) -> list[str]:
    try:
        rows = normalize._reservation_rows(payload)  # noqa: SLF001 - same package
    except normalize.VendorPayloadError:
        return []
    seen: list[str] = []
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _observed_statuses(payload: Any) -> list[str]:
    try:
        rows = normalize._reservation_rows(payload)  # noqa: SLF001 - same package
    except normalize.VendorPayloadError:
        return []
    seen: list[str] = []
    for row in rows:
        value = str(row.get("status") or "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def run_capture(
    client: BlueJayClient,
    out_root: Path | str,
    start: date,
    end: date,
    *,
    category_map: dict[str, str] | None = None,
    hotel_id: str | None = None,
) -> CaptureResult:
    """Make every planned request once, write raw + sanitized, report findings.

    Once each, deliberately. There is no retry loop: the windows are short and
    shared, and hammering a refused endpoint is the one behaviour most likely
    to lose us access.
    """
    out_root = Path(out_root)
    result = CaptureResult(
        raw_dir=out_root / RAW_DIRNAME, snapshot_dir=out_root / SNAPSHOT_DIRNAME
    )

    # Fail before writing anything if the window is shut: a half-written
    # snapshot directory that looks complete is worse than none.
    status = windows.window_status(client._now())  # noqa: SLF001 - same package
    if not status.is_open and not client.ignore_window:
        client.get(plan_requests(start, end)[0].endpoint)  # raises with remediation

    raw_payloads: dict[str, Any] = {}
    for step in plan_requests(start, end):
        try:
            payload = client.get(step.endpoint, step.params)
        except Exception as exc:  # noqa: BLE001 - one endpoint must not sink the rest
            # A missing endpoint is itself a finding worth keeping: several
            # paths in the document are internally inconsistent.
            result.errors.append(f"{step.name}: {type(exc).__name__}: {exc}")
            continue
        # RAW always, even for an error: it is evidence, and an error body is
        # often the most informative thing a first window produces — it is what
        # tells us the auth header guess was wrong.
        _write(result.raw_dir / f"{step.name}.json", payload)

        # Validate BEFORE treating it as data. An error carrying HTTP 200 was
        # being written to the snapshot like any success, producing a capture
        # that looked complete and asserted an empty hotel on every replay.
        try:
            normalize._check_envelope(payload)  # noqa: SLF001 - same package
        except normalize.VendorPayloadError as exc:
            result.errors.append(f"{step.name}: {exc}")
            continue

        # A filter endpoint with no rows is not "a property with no rooms", it
        # is a shape we misread — and it sets units_total to 0 for every
        # category, which makes occupancy undefined across the horizon.
        if step.allowlist is not None and step.name != "source-list":
            rows_seen = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows_seen, list) or not rows_seen:
                result.errors.append(
                    f"{step.name}: returned no rows in a shape we recognise "
                    f"({type(rows_seen).__name__}). Check the raw file — the response "
                    f"schema for this endpoint is undocumented and inferred."
                )
                continue

        raw_payloads[step.name] = payload

        if step.name == "reservation":
            clean: Any = sanitize.sanitize_reservations(payload)
            result.observed_statuses = _observed_statuses(payload)
            result.reservation_room_type_names = _distinct(payload, "roomType")
        elif step.allowlist is not None:
            rows = payload.get("data") if isinstance(payload, dict) else payload
            clean = {"data": sanitize.sanitize_rows(rows, step.allowlist)}
        else:
            # No personal data documented, but pass through json round-trip so
            # the snapshot is always plain data rather than whatever came back.
            clean = payload
        _write(result.snapshot_dir / f"{step.name}.json", clean)

    room_type_rows = []
    payload = raw_payloads.get("roomtype-list")
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        room_type_rows = [r for r in payload["data"] if isinstance(r, dict)]
    elif isinstance(payload, list):
        room_type_rows = [r for r in payload if isinstance(r, dict)]
    result.unmapped_room_types = normalize.unmapped_room_type_ids(
        room_type_rows, category_map or {}
    )

    # ONE roomdetail call per room type. A real roomdetail row has no
    # roomtypeId, so this is the only way a snapshot can count units per type.
    for row in room_type_rows:
        type_id = str(
            normalize._first(row, "roomtypeId", "roomTypeId", "id", default="") or ""  # noqa: SLF001
        ).strip()
        if not type_id:
            continue
        try:
            payload = client.get("roomdetail-list", {"roomtypeId": type_id})
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"roomdetail-list[{type_id}]: {type(exc).__name__}: {exc}")
            continue
        _write(result.raw_dir / f"roomdetail-list-{type_id}.json", payload)
        rows = payload.get("data") if isinstance(payload, dict) else payload
        _write(
            result.snapshot_dir / f"roomdetail-list-{type_id}.json",
            {"data": sanitize.sanitize_rows(rows, sanitize.ROOM_DETAIL_ALLOWLIST)},
        )
    result.filter_room_type_names = [
        name
        for name in (
            str(normalize._first(r, "roomtypeName", "roomTypeName", "name", default="") or "").strip()  # noqa: SLF001
            for r in room_type_rows
        )
        if name
    ]

    _write(
        result.snapshot_dir / "meta.json",
        {
            "captured_at": datetime.now(tz=windows.VIETNAM).isoformat(),
            "hotel_id": str(hotel_id or client.hotel_id),
            # Only true if something was actually captured AND sanitised. A
            # run where every request failed used to write `sanitised: true`
            # over an empty directory, which the snapshot provider then read as
            # a healthy capture.
            "sanitised": bool(raw_payloads),
            # A snapshot pseudonymised with the public fixture salt is
            # reversible in about a second; whoever loads it must be told.
            "salt_is_private": sanitize.salt_is_private(),
            "category_map": dict(category_map or {}),
            "window_range": {"from": start.isoformat(), "to": end.isoformat()},
            "observed_statuses": result.observed_statuses,
            "reservation_room_type_names": result.reservation_room_type_names,
            "filter_room_type_names": result.filter_room_type_names,
            "errors": result.errors,
            # Never the base URL with credentials, never the key. The hotel id
            # is enough to know which tenant this came from.
        },
    )
    return result
