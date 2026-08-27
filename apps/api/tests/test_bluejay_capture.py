"""Raw capture and the sanitisation pipeline that turns it into a snapshot.

The window is short and shared, so a capture has to be right the first time:
one pass, every endpoint, raw kept for diffing against the documentation and a
sanitized copy produced separately.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from dynamic_pricing.providers.pms.base import ProviderUnavailable
from dynamic_pricing.providers.pms.bluejay import capture as cap
from dynamic_pricing.providers.pms.bluejay.client import BlueJayClient

VN = ZoneInfo("Asia/Ho_Chi_Minh")
INSIDE = datetime(2026, 5, 21, 16, 30, tzinfo=VN)
OUTSIDE = datetime(2026, 5, 21, 12, 0, tzinfo=VN)

RESERVATION_BODY = {
    "data": {
        "type": "reservation",
        "attributes": {
            "reservations": [
                {
                    "bookingCode": "003289",
                    "referenceCode": "OTA-77",
                    "guestName": "Nguyễn Văn A",
                    "guestImagepaper": "/uploads/passport-12345.jpg",
                    "roomType": "Căn hộ 3 phòng ngủ",
                    "roomName": "B - 2",
                    "source": "CTV THƯ",
                    "status": "Đã huỷ",
                    "bookDate": "2026-05-18 00:00:00",
                    "checkInTime": "2026-05-21",
                    "checkOutTime": "2026-05-22",
                    "night": 1,
                    "roomPrice": 4_725_000,
                    "payment": 4_725_000,
                    "balance": 0,
                    "deposit": 0,
                    "note": ["allergic to shellfish"],
                }
            ]
        },
    }
}


def _client(now=INSIDE):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("reservation"):
            return httpx.Response(200, json=RESERVATION_BODY)
        return httpx.Response(200, json={"data": [{"roomtypeId": 6153, "roomtypeName": "X"}]})

    return BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        transport=httpx.MockTransport(handler),
        now=lambda: now,
    )


# =========================================================================
def test_a_dry_run_makes_no_calls_at_all():
    """The default has to be safe: running the probe to see what it WOULD do
    must not spend a request from a shared, ninety-minute-a-day budget."""
    client = _client()
    plan = cap.plan_requests(date(2026, 5, 1), date(2026, 6, 1))
    assert plan and client.calls_made == 0


def test_the_plan_covers_every_endpoint_the_adapter_depends_on():
    names = {step.name for step in cap.plan_requests(date(2026, 5, 1), date(2026, 6, 1))}
    assert {"roomtype-list", "roomdetail-list", "reservation"} <= names


def test_the_plan_asks_reservations_by_stay_night():
    """dateType=3 is what makes one endpoint yield bookings, occupancy AND a
    derived rate — which matters when the window is thirty minutes."""
    step = next(s for s in cap.plan_requests(date(2026, 5, 1), date(2026, 6, 1)) if s.name == "reservation")
    assert step.params["dateType"] == 3


def test_a_capture_outside_the_window_refuses_before_sending(tmp_path):
    with pytest.raises(ProviderUnavailable):
        cap.run_capture(_client(now=OUTSIDE), tmp_path, date(2026, 5, 1), date(2026, 6, 1))


def test_raw_and_sanitized_are_written_to_separate_directories(tmp_path):
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert result.raw_dir != result.snapshot_dir
    assert (result.raw_dir / "reservation.json").is_file()
    assert (result.snapshot_dir / "reservation.json").is_file()


def test_the_raw_capture_keeps_everything_for_diffing_against_the_document(tmp_path):
    """Raw is how we learn what live actually returns. It is gitignored and
    never leaves the machine."""
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    raw = (result.raw_dir / "reservation.json").read_text(encoding="utf-8")
    assert "guestName" in raw


def test_the_snapshot_carries_no_guest_identity_whatsoever(tmp_path):
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    clean = (result.snapshot_dir / "reservation.json").read_text(encoding="utf-8")
    for leaked in ("Nguyễn Văn A", "passport-12345", "allergic to shellfish", "OTA-77"):
        assert leaked not in clean


def test_the_snapshot_records_whether_its_pseudonyms_are_actually_protected(
    tmp_path, monkeypatch
):
    """A snapshot pseudonymised with the public fixture salt is reversible in
    under a second. Whoever loads it must be told.

    Both directions, and the environment is CONTROLLED. An earlier version
    asserted only `False` and passed purely because no salt happened to be set
    on the machine — so the moment a real one was configured, a correct system
    failed a test that was measuring its own surroundings.
    """
    monkeypatch.delenv("BLUEJAY_PSEUDONYM_SALT", raising=False)
    result = cap.run_capture(_client(), tmp_path / "public", date(2026, 5, 1), date(2026, 6, 1))
    meta = json.loads((result.snapshot_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["salt_is_private"] is False
    assert meta["sanitised"] is True

    monkeypatch.setenv("BLUEJAY_PSEUDONYM_SALT", "a-private-salt")
    result = cap.run_capture(_client(), tmp_path / "private", date(2026, 5, 1), date(2026, 6, 1))
    meta = json.loads((result.snapshot_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["salt_is_private"] is True


def test_the_snapshot_records_when_it_was_captured(tmp_path):
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    meta = json.loads((result.snapshot_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["captured_at"]


def test_the_capture_reports_which_status_strings_were_actually_seen(tmp_path):
    """The single highest-value output of the first window: our status
    vocabulary is nine guesses and one observation, and a WRONG guess does not
    raise — it silently miscounts occupancy."""
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert "Đã huỷ" in result.observed_statuses


def test_the_capture_reports_room_types_that_still_need_mapping(tmp_path):
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert ("6153", "X") in result.unmapped_room_types


def test_a_capture_never_writes_the_api_key_anywhere(tmp_path):
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    for path in list(result.raw_dir.rglob("*")) + list(result.snapshot_dir.rglob("*")):
        if path.is_file():
            assert "k" != path.read_text(encoding="utf-8").strip()
            assert "api_key" not in path.read_text(encoding="utf-8")


def test_the_capture_reports_both_room_type_name_vocabularies(tmp_path):
    """Reservations join to room types by NAME, and the filter endpoint may not
    use the same names. Dumping both sets turns a speculative design decision
    into an observation on the very first run — if they intersect the name join
    is safe, if they are disjoint we see it immediately."""
    result = cap.run_capture(_client(), tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert "Căn hộ 3 phòng ngủ" in result.reservation_room_type_names
    assert "X" in result.filter_room_type_names


def test_an_error_envelope_does_not_produce_a_clean_looking_snapshot(tmp_path):
    """D33 in the capture tool.

    An error carrying HTTP 200 was written to the snapshot like any success:
    six files, `sanitised: true`, no errors recorded — and the snapshot
    provider then reported it healthy while it asserted an empty hotel on every
    replay. A capture taken during a soft failure has to be recognisable AS one.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "message": "No access", "data": []})

    client = BlueJayClient(
        base_url="https://api-test.example/api/v2", api_key="k", hotel_id="1003",
        transport=httpx.MockTransport(handler), now=lambda: INSIDE,
    )
    result = cap.run_capture(client, tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert result.errors, "an error envelope must be recorded as an error"
    assert any("No access" in e for e in result.errors), "the vendor's reason must survive"

    meta = json.loads((result.snapshot_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["sanitised"] is False


def test_the_raw_response_is_kept_even_when_it_is_an_error(tmp_path):
    """Raw is EVIDENCE. An error body is often the most informative thing a
    first window produces, and it is what tells us the auth guess was wrong."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "message": "No access", "data": []})

    client = BlueJayClient(
        base_url="https://api-test.example/api/v2", api_key="k", hotel_id="1003",
        transport=httpx.MockTransport(handler), now=lambda: INSIDE,
    )
    result = cap.run_capture(client, tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert (result.raw_dir / "reservation.json").is_file()
    assert "No access" in (result.raw_dir / "reservation.json").read_text(encoding="utf-8")


def test_a_filter_endpoint_returning_no_rows_is_recorded_as_a_problem(tmp_path):
    """`{"data": {"items": []}}` sanitised to `{"data": []}` in silence. Zero
    room types is not a property with no rooms — it is a shape we misread, and
    it sets units_total to 0 for every category."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("reservation"):
            return httpx.Response(200, json={"data": {"type": "reservation", "attributes": {"reservations": []}}})
        return httpx.Response(200, json={"data": {"items": []}})

    client = BlueJayClient(
        base_url="https://api-test.example/api/v2", api_key="k", hotel_id="1003",
        transport=httpx.MockTransport(handler), now=lambda: INSIDE,
    )
    result = cap.run_capture(client, tmp_path, date(2026, 5, 1), date(2026, 6, 1))
    assert any("roomtype-list" in e for e in result.errors)
