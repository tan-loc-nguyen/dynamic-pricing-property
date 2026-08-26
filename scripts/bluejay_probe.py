#!/usr/bin/env python3
"""Read-only Blue Jay probe. Run this the moment a testing window opens.

    python scripts/bluejay_probe.py                 # window status only, NO calls
    python scripts/bluejay_probe.py --probe         # one GET per endpoint, prints shapes
    python scripts/bluejay_probe.py --capture       # --probe, plus raw + sanitized files

The default makes NO network calls. The windows are short and shared, so
running this to see what it would do must not spend a request.

This tool cannot write to Blue Jay: the client it uses exposes no verb but GET.

SECURITY
    Raw captures contain guest names and identity-document references. They are
    written under apps/api/captures/, which is gitignored, and this repository
    is public. Set BLUEJAY_PSEUDONYM_SALT before capturing anything real, or the
    snapshot's booking codes are recoverable in about a second.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from dynamic_pricing.config import get_settings  # noqa: E402
from dynamic_pricing.providers.pms.base import ProviderUnavailable  # noqa: E402
from dynamic_pricing.providers.pms.bluejay import capture, normalize, sanitize, windows  # noqa: E402
from dynamic_pricing.providers.pms.bluejay.client import BlueJayClient  # noqa: E402


def _describe(payload, depth: int = 0, limit: int = 3) -> list[str]:
    """The SHAPE of a response, not its contents.

    Printing values would put guest names on a terminal and into scrollback.
    The whole question during a window is "what are the field names", which
    this answers without showing a single one of them.
    """
    pad = "  " * depth
    if isinstance(payload, dict):
        out = []
        for key, value in list(payload.items())[:20]:
            if isinstance(value, (dict, list)):
                out.append(f"{pad}{key}:")
                out.extend(_describe(value, depth + 1, limit))
            else:
                out.append(f"{pad}{key}: {type(value).__name__}")
        return out
    if isinstance(payload, list):
        if not payload:
            return [f"{pad}[] (empty)"]
        return [f"{pad}[{len(payload)} items], first item:"] + _describe(payload[0], depth + 1, limit)
    return [f"{pad}{type(payload).__name__}"]


def print_window() -> bool:
    status = windows.window_status()
    print(f"\nVietnam time now : {status.now_vn:%Y-%m-%d %H:%M:%S} (Asia/Ho_Chi_Minh)")
    print("Testing windows  :")
    for w in windows.TESTING_WINDOWS:
        mark = "confirmed" if w.confirmed else "UNCONFIRMED — never called automatically"
        print(f"  {w.source_text:<14} {mark}")
        if w.note:
            print(f"      {w.note}")
    if status.is_open:
        print("\n  >> WINDOW IS OPEN. Capture now.\n")
    else:
        opens = status.next_open_at.strftime("%H:%M on %d %b") if status.next_open_at else "unknown"
        mins = status.seconds_until_open // 60
        print(f"\n  >> Window is CLOSED. Next opens {opens} (in {mins} min).\n")
    return status.is_open


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", action="store_true", help="make one GET per endpoint and print response SHAPES")
    parser.add_argument("--capture", action="store_true", help="probe, and write raw + sanitized files")
    parser.add_argument("--days", type=int, default=90, help="forward days of reservations to request")
    parser.add_argument("--out", default=None, help="output directory (default apps/api/captures/<date>)")
    parser.add_argument(
        "--i-was-told-the-window-moved",
        action="store_true",
        help="bypass the window check. Only when Blue Jay has said so on a call.",
    )
    args = parser.parse_args()

    is_open = print_window()
    if not (args.probe or args.capture):
        print("Nothing else to do (no --probe or --capture). No requests were made.")
        return 0

    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("BLUEJAY_BASE_URL", settings.bluejay_base_url),
            ("BLUEJAY_API_KEY", settings.bluejay_api_key),
            ("BLUEJAY_HOTEL_ID", settings.bluejay_hotel_id),
        )
        if not value
    ]
    if missing:
        print(f"Not configured. Set {', '.join(missing)} in .env (never commit them).")
        return 2

    if not is_open and not args.i_was_told_the_window_moved:
        print("Refusing to call outside the testing window. Re-run when it opens.")
        return 3

    if args.capture and not sanitize.salt_is_private():
        print(
            "WARNING: BLUEJAY_PSEUDONYM_SALT is not set, so the snapshot's booking codes\n"
            "         are recoverable from the public fixture salt. Set it and re-capture\n"
            "         before sharing this snapshot with anyone.\n"
        )

    client = BlueJayClient(
        base_url=settings.bluejay_base_url,
        api_key=settings.bluejay_api_key,
        hotel_id=settings.bluejay_hotel_id,
        timeout=settings.bluejay_timeout_seconds,
        ignore_window=args.i_was_told_the_window_moved,
    )

    today = date.today()
    start, end = today, today + timedelta(days=args.days)

    if args.capture:
        out = Path(args.out) if args.out else REPO_ROOT / "apps" / "api" / "captures" / today.isoformat()
        result = capture.run_capture(client, out, start, end, hotel_id=settings.bluejay_hotel_id)
        print(f"raw      -> {result.raw_dir}   (GITIGNORED: contains guest data)")
        print(f"snapshot -> {result.snapshot_dir}\n")
        if result.errors:
            print("Endpoints that failed (each one is a finding):")
            for err in result.errors:
                print(f"  ! {err}")
        print("\nSTATUS STRINGS OBSERVED — the highest-value output of this window.")
        print("Our vocabulary is nine inferences and one observation, and a wrong")
        print("inference does not raise, it silently miscounts occupancy:")
        for value in result.observed_statuses or ["(none seen)"]:
            known = normalize.status_meaning(value)
            verdict = f"known, occupies={known.occupies}" if known else "NOT IN OUR VOCABULARY"
            print(f"  {value!r:<28} {verdict}")
        print("\nStill inferred, awaiting an observation:")
        for value in normalize.provisional_status_strings():
            print(f"  {value!r}")
        # Reservations join to room types by NAME. Nothing guarantees the
        # reservation payload and the filter endpoint use the same vocabulary,
        # and the document's one id/name pairing matches neither reservation
        # sample. Printing both sets settles it on the first run instead of
        # leaving it to be discovered when a sync fails.
        in_reservations = set(result.reservation_room_type_names)
        in_filter = set(result.filter_room_type_names)
        print("\nROOM TYPE NAME VOCABULARIES")
        print(f"  in reservations : {sorted(in_reservations) or '(none)'}")
        print(f"  in roomtype-list: {sorted(in_filter) or '(none)'}")
        if in_reservations and in_filter:
            if in_reservations & in_filter:
                print("  -> They intersect. The name join is safe.")
            else:
                print("  -> DISJOINT. The name join CANNOT work. Switch to querying")
                print("     /reservation once per room type with roomTypes=<id>.")
            orphans = sorted(in_reservations - in_filter)
            if orphans:
                print(f"  -> Seen in reservations but NOT in roomtype-list: {orphans}")

        if result.unmapped_room_types:
            print("\nRoom types with no category mapping (Settings -> Data):")
            for type_id, name in result.unmapped_room_types:
                print(f"  id={type_id!r}  name={name!r}")
        print(f"\nRequests made: {client.calls_made}")
        return 0

    for step in capture.plan_requests(start, end):
        print(f"\n--- {step.name} ---")
        try:
            payload = client.get(step.endpoint, step.params)
        except ProviderUnavailable as exc:
            print(f"  ! {exc.message}")
            continue
        for line in _describe(payload):
            print(f"  {line}")
    print(f"\nRequests made: {client.calls_made}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
