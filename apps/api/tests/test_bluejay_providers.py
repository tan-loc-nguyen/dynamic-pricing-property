"""Live / Snapshot / Mock provider architecture, and the read-only guarantee.

The user's instruction was explicit: Blue Jay is READ-ONLY, because whether
they operate a zero-data-retention policy is unknown and the safe assumption is
that a write could be destructive or irreversible. "We only send GETs" is a
convention; these tests make it a property of the code.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from dynamic_pricing.providers.pms import get_pms_provider, list_pms_providers
from dynamic_pricing.providers.pms.base import ProviderUnavailable
from dynamic_pricing.providers.pms.bluejay import client as bj_client
from dynamic_pricing.providers.pms.bluejay.snapshot import SnapshotPMSProvider

VN = ZoneInfo("Asia/Ho_Chi_Minh")
INSIDE_WINDOW = datetime(2026, 5, 21, 16, 30, tzinfo=VN)
OUTSIDE_WINDOW = datetime(2026, 5, 21, 12, 0, tzinfo=VN)


# ------------------------------------------------------------------ helpers
def _capture(tmp_path):
    """A minimal SANITISED capture, in the on-disk shape the probe writes."""
    root = tmp_path / "demo"
    root.mkdir()
    (root / "meta.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-05-21T16:05:00+07:00",
                "hotel_id": "1003",
                "sanitised": True,
                "salt_is_private": True,
                "category_map": {"6153": "3br"},
            }
        ),
        encoding="utf-8",
    )
    (root / "roomtype-list.json").write_text(
        json.dumps({"data": [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}]}),
        encoding="utf-8",
    )
    rooms = {"data": [{"roomdetailId": i, "roomName": f"B - {i}"} for i in (1, 2)]}
    (root / "roomdetail-list.json").write_text(json.dumps(rooms), encoding="utf-8")
    # Per-type file: a real roomdetail row has NO roomtypeId, so the capture
    # stores one file per room type, mirroring roomdetail-list?roomtypeId=.
    (root / "roomdetail-list-6153.json").write_text(json.dumps(rooms), encoding="utf-8")
    (root / "reservation.json").write_text(
        json.dumps(
            {
                "data": {
                    "type": "reservation",
                    "attributes": {
                        "reservations": [
                            {
                                "bookingCode": "BJ-AAAA",
                                "roomType": "Căn hộ 3 phòng ngủ",
                                "roomName": "B - 2",
                                "source": "Booking.com",
                                "status": "Đã xác nhận",
                                "bookDate": "2026-05-01 09:30:00",
                                "checkInTime": "2026-05-21",
                                "checkOutTime": "2026-05-23",
                                "night": 2,
                                "roomPrice": 4_000_000,
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return root


# =========================================================================
# 1. Read-only is structural, not a convention
# =========================================================================


def test_the_client_exposes_no_way_to_send_anything_but_a_get():
    """Blue Jay documents POST for creating bookings. We must never reach it."""
    for verb in ("post", "put", "patch", "delete", "request", "send"):
        assert not hasattr(bj_client.BlueJayClient, verb), (
            f"BlueJayClient.{verb} exists — a write path into a live PMS must not be "
            f"one attribute lookup away"
        )


def test_every_request_the_client_issues_is_a_get():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(200, json={"data": []})

    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        transport=httpx.MockTransport(handler),
        now=lambda: INSIDE_WINDOW,
    )
    client.get("reservation", {"dateType": 3})
    assert seen == ["GET"]


def test_the_api_key_never_appears_in_the_repr_of_the_client():
    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2", api_key="super-secret", hotel_id="1003"
    )
    assert "super-secret" not in repr(client)


# =========================================================================
# 2. The window is enforced at the only place that can enforce it
# =========================================================================


def test_a_call_outside_the_testing_window_is_refused_before_it_leaves():
    """"Do not call outside the documented windows" has to be a property of the
    client, not a rule a developer remembers at 08:15.

    Deliberately DIFFERENTIAL: it shows the same call reaching the network
    inside the window and not reaching it outside. Asserting only that the
    outside call raises would pass if `get()` were broken for any other reason.
    """
    reached: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(str(request.url))
        return httpx.Response(200, json={"data": []})

    def client_at(moment):
        return bj_client.BlueJayClient(
            base_url="https://api-test.example/api/v2",
            api_key="k",
            hotel_id="1003",
            transport=httpx.MockTransport(handler),
            now=lambda: moment,
        )

    client_at(INSIDE_WINDOW).get("reservation", {})
    assert len(reached) == 1, "inside the window the request must go through"

    with pytest.raises(ProviderUnavailable):
        client_at(OUTSIDE_WINDOW).get("reservation", {})
    assert len(reached) == 1, "outside it, the request must not reach the network at all"


def test_the_refusal_says_when_the_window_next_opens():
    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        now=lambda: OUTSIDE_WINDOW,
    )
    with pytest.raises(ProviderUnavailable) as excinfo:
        client.get("reservation", {})
    assert "16:00" in excinfo.value.remediation


def test_an_explicit_override_exists_for_the_moment_blue_jay_says_the_window_moved():
    """A hard block with no override becomes a blocker at the worst moment.
    It is opt-in per call and never the default."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        transport=httpx.MockTransport(handler),
        now=lambda: OUTSIDE_WINDOW,
        ignore_window=True,
    )
    assert client.get("reservation", {}) == {"data": []}


def test_the_hotel_id_is_attached_to_every_request():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"data": []})

    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        transport=httpx.MockTransport(handler),
        now=lambda: INSIDE_WINDOW,
    )
    client.get("roomtype-list", {})
    assert "hotelId=1003" in seen[0]


# =========================================================================
# 3. Snapshot mode — the preferred demo source
# =========================================================================


def test_a_snapshot_replays_through_the_very_same_normaliser_as_live(tmp_path):
    """A snapshot that needed its own parser would stop being evidence about
    the live response."""
    provider = SnapshotPMSProvider(_capture(tmp_path))
    bookings = provider.fetch_bookings(date(2026, 5, 1), date(2026, 6, 1))
    assert [b.stay_date for b in bookings] == [date(2026, 5, 21), date(2026, 5, 22)]


def test_a_snapshot_reports_units_from_the_captured_room_details(tmp_path):
    provider = SnapshotPMSProvider(_capture(tmp_path))
    room_types = provider.fetch_room_types()
    assert [(rt.external_id, rt.units_total) for rt in room_types] == [("3br", 2)]


def test_a_snapshot_provider_is_healthy_without_any_credentials(tmp_path):
    """The entire point: demo without the network, and without a testing window."""
    provider = SnapshotPMSProvider(_capture(tmp_path))
    assert provider.status().healthy is True


def test_a_missing_snapshot_fails_with_remediation_rather_than_empty_data(tmp_path):
    """Silently returning nothing would look like a property with no bookings."""
    provider = SnapshotPMSProvider(tmp_path / "does-not-exist")
    with pytest.raises(ProviderUnavailable) as excinfo:
        provider.fetch_room_types()
    assert excinfo.value.remediation


def test_a_snapshot_says_when_it_was_captured(tmp_path):
    """Demo data with no date silently becomes stale."""
    provider = SnapshotPMSProvider(_capture(tmp_path))
    assert "2026-05-21" in provider.status().detail


def test_a_snapshot_captured_with_the_public_salt_is_flagged_as_unprotected(tmp_path):
    """On its own warning channel — see the dedicated test below for why this
    must not travel through `unresolved_mappings`."""
    root = _capture(tmp_path)
    meta = json.loads((root / "meta.json").read_text())
    meta["salt_is_private"] = False
    (root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    provider = SnapshotPMSProvider(root)
    assert provider.status().warnings


# =========================================================================
# 4. All three modes are interchangeable
# =========================================================================


def test_all_three_data_modes_are_registered():
    assert {"mock", "snapshot", "bluejay"} <= set(list_pms_providers())


def test_every_registered_provider_satisfies_the_same_contract():
    """Interchangeable is the whole claim; a mode missing a method breaks it."""
    required = (
        "status", "fetch_properties", "fetch_room_types",
        "fetch_physical_rooms", "fetch_inventory", "fetch_bookings",
    )
    for name in ("mock", "snapshot", "bluejay"):
        provider = get_pms_provider(name)
        for method in required:
            assert callable(getattr(provider, method, None)), f"{name}.{method}"


def test_no_provider_will_push_a_rate_back_into_the_pms():
    """Shadow Mode (D22) plus the read-only instruction, checked per mode."""
    for name in ("mock", "snapshot", "bluejay"):
        provider = get_pms_provider(name)
        assert provider.supports_rate_push is False
        with pytest.raises(ProviderUnavailable):
            provider.push_rate("3br", date(2026, 5, 21), 1_000_000.0)


# =========================================================================
# 5. Rate provenance has to survive persistence, or it is decoration
# =========================================================================


def test_where_a_rate_came_from_survives_the_sync(tmp_path):
    """A realized ADR that persists indistinguishably from a published rate
    defeats the entire reason the field exists (decision 3).

    Blue Jay publishes no forward rate, so in LIVE and SNAPSHOT mode most
    rates are reconstructed. An operator reading an achieved average as a list
    price is exactly the confusion this has to prevent.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from dynamic_pricing.models import Base, StayDateInventory
    from dynamic_pricing.services.sync import sync_pms

    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}")
    Base.metadata.create_all(engine)

    provider = SnapshotPMSProvider(_capture(tmp_path))
    with Session(engine) as session:
        sync_pms(session, provider, start=date(2026, 5, 20), end=date(2026, 5, 24))
        rows = session.scalars(
            select(StayDateInventory).order_by(StayDateInventory.stay_date)
        ).all()
        provenances = {r.rate_provenance for r in rows}

    assert provenances, "the sync persisted no inventory at all"
    assert "derived_adr" in provenances, (
        "nights covered by a captured reservation must be marked as a DERIVED rate"
    )


def test_a_night_with_no_booking_is_not_labelled_as_a_derived_rate(tmp_path):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from dynamic_pricing.models import Base, StayDateInventory
    from dynamic_pricing.services.sync import sync_pms

    engine = create_engine(f"sqlite:///{tmp_path / 'sync2.db'}")
    Base.metadata.create_all(engine)

    provider = SnapshotPMSProvider(_capture(tmp_path))
    with Session(engine) as session:
        sync_pms(session, provider, start=date(2026, 5, 20), end=date(2026, 5, 24))
        empty = session.scalars(
            select(StayDateInventory).where(StayDateInventory.stay_date == date(2026, 5, 24))
        ).all()

    assert empty and all(r.rate_provenance != "derived_adr" for r in empty)


# =========================================================================
# 6. The LIVE provider — defensive, and honest about what it cannot do yet
# =========================================================================


def _live(handler, *, now=INSIDE_WINDOW, category_map=None):
    from dynamic_pricing.providers.pms.bluejay.provider import BlueJayPMSProvider

    return BlueJayPMSProvider(
        client=bj_client.BlueJayClient(
            base_url="https://api-test.example/api/v2",
            api_key="k",
            hotel_id="1003",
            transport=httpx.MockTransport(handler),
            now=lambda: now,
        ),
        category_map=category_map if category_map is not None else {"6153": "3br"},
    )


def _routes(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("roomtype-list"):
        return httpx.Response(200, json={"data": [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}]})
    if path.endswith("roomdetail-list"):
        # The real API filters by roomtypeId; returning everything regardless
        # is what an IGNORED filter looks like, and the adapter refuses that.
        tid = request.url.params.get("roomtypeId")
        if tid is None:  # unfiltered: the whole property
            rooms = [{"roomdetailId": i, "roomName": f"B - {i}"} for i in (1, 2, 3)]
        else:
            rooms = [{"roomdetailId": i, "roomName": f"B - {i}"} for i in (1, 2)] if tid == "6153" else []
        return httpx.Response(200, json={"data": rooms})
    if path.endswith("source-list"):
        return httpx.Response(200, json={"data": [{"id": 1, "sourceName": "Direct", "commiission": 0}]})
    if path.endswith("report-room-occupancy"):
        return httpx.Response(200, json={"status": "Success", "message": "ok", "data": {
            "GrandTotal": {"RoomTypes": [
                {"RoomTypeId": 6153, "RoomTypeName": "Căn hộ 3 phòng ngủ", "DailyDetails": [
                    {"Date": "21/05/2026", "RoomOccupied": 1, "Blocked": 0,
                     "TotalRoom": 2, "EmptyRoom": 1, "OccupancyRate": 50.0}]}]}}})
    if path.endswith("reservation"):
        return httpx.Response(
            200,
            json={
                "data": {
                    "type": "reservation",
                    "attributes": {
                        "reservations": [
                            {
                                "bookingCode": "1",
                                "roomType": "Căn hộ 3 phòng ngủ",
                                "roomName": "B - 1",
                                "source": "Direct",
                                "status": "Đã xác nhận",
                                "bookDate": "2026-05-01 00:00:00",
                                "checkInTime": "2026-05-21",
                                "checkOutTime": "2026-05-22",
                                "night": 1,
                                "roomPrice": 3_000_000,
                            }
                        ]
                    },
                }
            },
        )
    return httpx.Response(404, json={})


def test_the_live_provider_maps_a_reservation_all_the_way_to_a_booking_dto():
    out = _live(_routes).fetch_bookings(date(2026, 5, 1), date(2026, 6, 1))
    assert [(b.room_type_external_id, b.stay_date, b.net_rate) for b in out] == [
        ("3br", date(2026, 5, 21), 3_000_000.0)
    ]


def test_the_live_provider_counts_units_from_the_room_detail_endpoint():
    assert [rt.units_total for rt in _live(_routes).fetch_room_types()] == [2]


def test_the_live_provider_refuses_to_sync_with_no_category_mapping():
    """Every room type unmapped means every date unpriced. That must be a clear
    refusal naming the fix, not an empty result."""
    with pytest.raises(ProviderUnavailable) as excinfo:
        _live(_routes, category_map={}).fetch_room_types()
    assert "Settings" in excinfo.value.remediation or "map" in excinfo.value.remediation.lower()


def test_an_http_error_from_blue_jay_never_looks_like_an_empty_hotel():
    """Zero bookings is the strongest discount signal the engine has."""
    with pytest.raises(ProviderUnavailable):
        _live(lambda _request: httpx.Response(401, json={"message": "bad key"})).fetch_bookings(
            date(2026, 5, 1), date(2026, 6, 1)
        )


def test_the_live_provider_status_names_the_testing_window():
    status = _live(_routes).status()
    assert "16:00" in status.detail or "16:00" in status.remediation


def test_the_live_provider_reports_room_types_the_operator_has_not_mapped():
    status = _live(_routes, category_map={}).status()
    assert any("6153" in note or "Căn hộ" in note for note in status.unresolved_mappings)


def test_a_public_salt_snapshot_warns_rather_than_filing_a_mapping_gap(tmp_path):
    """"Booking codes are trivially recoverable" is not a mapping nit."""
    root = _capture(tmp_path)
    meta = json.loads((root / "meta.json").read_text())
    meta["salt_is_private"] = False
    (root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    status = SnapshotPMSProvider(root).status()
    assert any("salt" in w.lower() or "recover" in w.lower() for w in status.warnings)
    assert not status.unresolved_mappings


def test_an_unsanitised_snapshot_warns_that_it_may_hold_guest_data(tmp_path):
    root = _capture(tmp_path)
    meta = json.loads((root / "meta.json").read_text())
    meta["sanitised"] = False
    (root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert any("guest" in w.lower() for w in SnapshotPMSProvider(root).status().warnings)


def test_a_properly_captured_snapshot_raises_no_warnings(tmp_path):
    """The warnings only mean something if a clean capture is silent."""
    assert SnapshotPMSProvider(_capture(tmp_path)).status().warnings == []


# =========================================================================
# 7. Review round 3
# =========================================================================


def test_a_missing_hotel_id_is_not_reported_as_a_healthy_integration():
    """Two predicates that should be one, disagreeing — the same shape as the
    demo_mode bug. `_configured` omitted hotel_id while `_api()` required it,
    so the panel said healthy and every fetch raised. BLUEJAY_HOTEL_ID is new
    in this slice, so it is the setting most likely to be missing on a first run.
    """
    import os
    from dynamic_pricing.config import get_settings
    from dynamic_pricing.providers.pms.bluejay.provider import BlueJayPMSProvider

    get_settings.cache_clear()
    saved = {k: os.environ.get(k) for k in ("BLUEJAY_BASE_URL", "BLUEJAY_API_KEY", "BLUEJAY_HOTEL_ID")}
    os.environ["BLUEJAY_BASE_URL"] = "https://api-test.example/api/v2"
    os.environ["BLUEJAY_API_KEY"] = "k"
    os.environ.pop("BLUEJAY_HOTEL_ID", None)
    try:
        get_settings.cache_clear()
        status = BlueJayPMSProvider().status()
        assert status.healthy is False
        assert "HOTEL_ID" in status.remediation
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def test_an_error_envelope_carrying_an_empty_list_is_not_read_as_no_room_types():
    """A very ordinary API shape. On roomdetail-list it sets units_total to 0
    for every category — occupancy undefined across the horizon, silently."""
    provider = _live(lambda _r: httpx.Response(200, json={"status": "error", "message": "Invalid API key", "data": []}))
    with pytest.raises(ProviderUnavailable) as excinfo:
        provider.fetch_room_types()
    assert "Invalid API key" in str(excinfo.value) or "Invalid API key" in excinfo.value.remediation


def test_one_sync_does_not_re_fetch_the_same_endpoint_over_and_over():
    """The window is thirty minutes and shared. Both client.py and capture.py
    warn against hammering it; duplication gets there just as fast as retrying.
    """
    calls: list[str] = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _routes(request)

    provider = _live(counting)
    provider.fetch_room_types()
    provider.fetch_physical_rooms()
    provider.fetch_bookings(date(2026, 5, 1), date(2026, 5, 5))
    provider.fetch_inventory(date(2026, 5, 1), date(2026, 5, 5))

    room_type_calls = [c for c in calls if c.endswith("roomtype-list")]
    reservation_calls = [c for c in calls if c.endswith("reservation")]
    assert len(room_type_calls) == 1, f"roomtype-list fetched {len(room_type_calls)}x"
    assert len(reservation_calls) == 1, f"reservation fetched {len(reservation_calls)}x"


def test_a_capture_where_every_request_failed_is_not_reported_healthy(tmp_path):
    """Only meta.json is written when the window shuts mid-run, and the
    provider would say "Replaying a sanitized Blue Jay capture from…" right up
    until each fetch raised "file is missing"."""
    root = tmp_path / "broken"
    root.mkdir()
    (root / "meta.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-05-21T16:05:00+07:00",
                "hotel_id": "1003",
                "sanitised": True,
                "salt_is_private": True,
                "errors": ["reservation: ProviderUnavailable: window closed"],
            }
        ),
        encoding="utf-8",
    )
    status = SnapshotPMSProvider(root).status()
    assert status.healthy is False


def test_what_the_adapter_could_not_vouch_for_reaches_the_sync_report(tmp_path):
    """A discrepancy recorded into a report nobody reads is a passing test and
    a silent product. The orphan-rooms warning says occupancy is OVERSTATED and
    recommendations biased upward — that has to reach a human."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from dynamic_pricing.models import Base
    from dynamic_pricing.services.sync import sync_pms

    engine = create_engine(f"sqlite:///{tmp_path / 'rep.db'}")
    Base.metadata.create_all(engine)
    provider = SnapshotPMSProvider(_capture(tmp_path))
    with Session(engine) as session:
        report = sync_pms(session, provider, start=date(2026, 5, 20), end=date(2026, 5, 24))
    assert "normalisation" in report.as_dict()


def test_a_horizon_crossing_a_season_boundary_does_not_reuse_one_seasons_band():
    """Measured: a 90-day window from late August gave every date High Season 1's
    2,300,000 — +9.5% on Low Season 2 dates and -8% on High Season 2 dates.
    It lands in change_pct, so it moves the calendar's change column and the
    bigChange threshold on precisely the far-out dates nobody can sanity-check.
    """
    provider = _live(_routes)
    rows = provider.fetch_inventory(date(2026, 8, 27), date(2026, 11, 24))
    rates = {r.stay_date: r.current_net_rate for r in rows if r.rate_provenance == "seasonal_base"}
    assert rates, "no seasonal_base rows to check"
    assert len(set(rates.values())) > 1, (
        "every date got the same seasonal base across a horizon spanning three seasons"
    )


# =========================================================================
# 8. The auth header name is a GUESS and must be changeable without a deploy
# =========================================================================


def test_the_api_key_goes_in_a_configurable_header():
    """The document says the key goes in "the Header" and never names it.

    `X-API-KEY` is our guess. If it is wrong every call 401s, and discovering
    that inside a thirty-minute shared window is not the moment to be editing
    source. One .env line has to be enough to try another.
    """
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"data": []})

    client = bj_client.BlueJayClient(
        base_url="https://api-test.example/api/v2",
        api_key="k",
        hotel_id="1003",
        auth_header="Authorization",
        auth_style="bearer",
        transport=httpx.MockTransport(handler),
        now=lambda: INSIDE_WINDOW,
    )
    client.get("reservation", {})
    assert seen[0]["authorization"] == "Bearer k"


def test_the_default_header_is_the_one_the_live_api_actually_accepts():
    """VERIFIED 2026-08-27 against api1.bluejaypms.com: `apikey`, raw.

    Was `X-API-KEY`, a guess. Real behaviour is authoritative, so the guess
    loses. It was found by noticing that `apikey` was the only variant
    returning 404 instead of 200-Unauthorized — a 404 means the request got
    PAST the auth gate and into routing.
    """
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"data": []})

    client = bj_client.BlueJayClient(
        base_url="https://api1.example/api/v2",
        api_key="k",
        hotel_id="1003",
        transport=httpx.MockTransport(handler),
        now=lambda: INSIDE_WINDOW,
    )
    client.get("reservation", {})
    assert seen[0]["apikey"] == "k"


def test_the_unresolved_list_does_not_carry_settled_questions():
    """`unresolved_mappings` is RENDERED to the operator.

    It began as fifteen entries written before we could call the API. Most were
    answered by observation, and a panel that keeps asking settled questions
    teaches whoever reads it to skip the panel — which is where the questions
    that DO matter live.

    So each phrase below names something we verified, and must not appear.
    """
    from dynamic_pricing.providers.pms.bluejay.provider import UNRESOLVED_MAPPINGS

    blob = " ".join(UNRESOLVED_MAPPINGS).lower()
    settled = {
        "which header": "the auth header is verified as `apikey`, raw",
        "x-api-key": "that was the wrong guess; the answer is `apikey`",
        "stay total or a nightly": "verified: roomPrice is the stay total",
        "only 'đã huỷ' has ever been observed": "the whole status mapping is verified",
        "response schema for roomtype-list": "both schemas are verified",
        "pagination beyond": "verified: page until a SHORT page; meta.total is capped",
        "correct endpoint for occupancy": "verified: /report-room-occupancy",
    }
    for phrase, why in settled.items():
        assert phrase not in blob, f"still asking a settled question ({phrase!r}) — {why}"


def test_the_unresolved_list_still_names_what_actually_blocks_us():
    """The counterpart: trimming must not quietly drop a real blocker."""
    from dynamic_pricing.providers.pms.bluejay.provider import UNRESOLVED_MAPPINGS

    blob = " ".join(UNRESOLVED_MAPPINGS).lower()
    for phrase in ("hotelid", "net or gross", "yield management"):
        assert phrase in blob, f"{phrase!r} is still unresolved and must stay listed"


# =========================================================================
# 9. The provider wired to the VERIFIED contract
# =========================================================================

def _api1_routes(reservation_pages=1, rows_per_page=2):
    """Mimics the real api1: {status,message,data} for filters, {meta,data} for
    reservations, roomdetail filtered by roomtypeId, source-list commissions."""
    ROOMS = {"6153": [{"id": 1, "roomName": "R - 401"}, {"id": 2, "roomName": "R - 402"}],
             "6154": [{"id": 11, "roomName": "DB(1) - 401"}]}
    def handler(request: httpx.Request) -> httpx.Response:
        path, q = request.url.path, request.url.params
        if path.endswith("roomtype-list"):
            return httpx.Response(200, json={"status": "Success", "message": "ok", "data": [
                {"id": 6153, "name": "Căn hộ 02 phòng ngủ", "code": "TPL"},
                {"id": 6154, "name": "Ninh Bình", "code": "DB"}]})
        if path.endswith("roomdetail-list"):
            tid = q.get("roomtypeId")
            rows = ROOMS.get(str(tid), [r for v in ROOMS.values() for r in v])
            return httpx.Response(200, json={"status": "Success", "message": "ok", "data": rows})
        if path.endswith("source-list"):
            return httpx.Response(200, json={"status": "Success", "message": "ok", "data": [
                {"id": 1, "sourceName": "BE", "commiission": 0},
                {"id": 2, "sourceName": "Viettravel", "commiission": 10}]})
        if path.endswith("reservation"):
            page = int(q.get("page", 1))
            limit = int(q.get("limit", 20))
            # Mimic a full page: the real API fills up to `limit`, and a SHORT
            # page is the only reliable end-of-data marker.
            n = limit if page < reservation_pages else (rows_per_page if page == reservation_pages else 0)
            if page > reservation_pages:
                rows = []
            else:
                rows = [{"bookingCode": f"C{page}-{i}", "roomType": "Căn hộ 02 phòng ngủ",
                         "roomName": "R - 401", "source": "BE", "status": "Đã xác nhận",
                         "bookDate": "2026-05-01 09:00:00", "checkInTime": "2026-05-21",
                         "checkOutTime": "2026-05-22", "night": 1, "roomPrice": 500000}
                        for i in range(n)]
            return httpx.Response(200, json={"meta": {"limit": rows_per_page, "page": page,
                                                      "total": len(rows)},
                                             "data": {"type": "reservation",
                                                      "attributes": {"reservations": rows}}})
        if path.endswith("report-room-occupancy"):
            return httpx.Response(200, json={"status": "Success", "message": "ok", "data": {
                "GrandTotal": {"GrandTotalRoomOccupied": 1, "GrandTotalBlocked": 0,
                               "GrandTotalRoom": 3, "GrandTotalRoomEmpty": 2,
                               "GrandTotalOccupancyRate": 33.3, "RoomTypes": [
                    {"RoomTypeId": 6153, "RoomTypeName": "Căn hộ 02 phòng ngủ",
                     "DailyDetails": [{"Date": "21/05/2026", "RoomOccupied": 1, "Blocked": 0,
                                       "TotalRoom": 2, "EmptyRoom": 1, "OccupancyRate": 50.0}]}]}}})
        return httpx.Response(404, json={})
    return handler


def _live_api1(handler, category_map=None):
    from dynamic_pricing.providers.pms.bluejay.provider import BlueJayPMSProvider
    return BlueJayPMSProvider(
        client=bj_client.BlueJayClient(base_url="https://api1.example/api/v2", api_key="k",
                                       hotel_id="1003", transport=httpx.MockTransport(handler),
                                       now=lambda: INSIDE_WINDOW),
        category_map=category_map if category_map is not None
        else {"6153": "2br_regular", "6154": "3br"})


def test_units_are_counted_by_calling_roomdetail_once_per_room_type():
    """The verified shape: roomdetail rows have no roomtypeId."""
    out = _live_api1(_api1_routes()).fetch_room_types()
    assert {(d.external_id, d.units_total) for d in out} == {("2br_regular", 2), ("3br", 1)}


def test_the_provider_pages_through_every_reservation():
    """`meta.total` is CAPPED AT `limit` — proven live. Stopping after page 1
    silently truncates, understating occupancy and pushing prices down."""
    pages: list[int] = []
    base = _api1_routes(reservation_pages=3, rows_per_page=2)
    def handler(request):
        if request.url.path.endswith("reservation"):
            pages.append(int(request.url.params.get("page", 1)))
        return base(request)
    out = _live_api1(handler).fetch_bookings(date(2026, 5, 1), date(2026, 5, 28))
    assert pages == [1, 2, 3], f"must page until a SHORT page, got {pages}"
    assert len(out) > 2, "rows from later pages must be kept"


def test_paging_stops_when_a_page_is_short(): 
    out = _live_api1(_api1_routes(reservation_pages=1, rows_per_page=2)).fetch_bookings(
        date(2026, 5, 1), date(2026, 5, 28))
    assert len(out) == 2


def test_occupancy_comes_from_the_occupancy_report_not_from_reservations():
    """The two disagree on ~3% of room-nights and the rule is unknown, so the
    PMS's own answer wins and reservations supply bookDate/pickup/rate."""
    inv = _live_api1(_api1_routes()).fetch_inventory(date(2026, 5, 21), date(2026, 5, 21))
    row = next(r for r in inv if r.room_type_external_id == "2br_regular")
    assert (row.units_total, row.units_sold) == (2, 1)


def test_a_window_wider_than_one_month_is_chunked():
    """VERIFIED constraint: report-room-occupancy rejects a range over a month."""
    seen: list[tuple[str, str]] = []
    base = _api1_routes()
    def handler(request):
        if request.url.path.endswith("report-room-occupancy"):
            seen.append((request.url.params.get("from"), request.url.params.get("to")))
        return base(request)
    _live_api1(handler).fetch_inventory(date(2026, 5, 1), date(2026, 8, 15))
    assert len(seen) >= 4, f"a 106-day window must be split, got {seen}"
    for f, t in seen:
        assert (date.fromisoformat(t) - date.fromisoformat(f)).days <= 27, (f, t)
