"""Provisional Blue Jay contract, derived from the API documentation ONLY.

=============================================================================
 STATUS: PROVISIONAL. Every fixture in this file comes from
 BLUE_JAY_BE_API_Report_EN.md, not from a live call. The documentation is
 known to be internally inconsistent (see docs/BLUEJAY_CONTRACT.md), so these
 tests pin what we BELIEVE the contract is, so that the first live response
 can be diffed against a written-down expectation instead of against nobody's
 memory.

 When the real API is observed, tests that disagree with it are WRONG and get
 corrected — real behaviour becomes authoritative. That is the point of
 writing them now.
=============================================================================
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from dynamic_pricing.providers.pms.bluejay import normalize, sanitize, windows

VN = ZoneInfo("Asia/Ho_Chi_Minh")


# ---------------------------------------------------------------- fixtures
# Verbatim from the "Sample Response" block of the reservation endpoint.
DOC_RESERVATION_PAYLOAD = {
    "meta": {"page": 1, "limit": 20, "total": 15},
    "data": {
        "type": "reservation",
        "attributes": {
            "reservations": [
                {
                    "bookingCode": "003283",
                    "referenceCode": "",
                    "guestName": "Ghép đoàn Hà test",
                    "roomType": "Holo Ben Thanh - 1 PN",
                    "roomName": "H - d3",
                    "source": "CTV THƯ",
                    "status": "Đã huỷ",
                    "bookDate": "2026-05-18 00:00:00",
                    "checkInTime": "2026-05-21",
                    "arrivalTime": "15:00:00",
                    "checkOutTime": "2026-05-22",
                    "departureTime": "12:00:00",
                    "night": 1,
                    "roomPrice": 0,
                    "servicePrice": 0,
                    "totalPrice": 0,
                    "payment": 0,
                    "balance": 0,
                    "deposit": 0,
                    "note": [],
                    "guestImagepaper": None,
                },
                {
                    "bookingCode": "003289",
                    "referenceCode": None,
                    "guestName": " Ha",
                    "roomType": "Căn hộ 3 phòng ngủ",
                    "roomName": "B - 2",
                    "source": "CTV THƯ",
                    "status": "Đã huỷ",
                    "bookDate": "2026-05-18 00:00:00",
                    "checkInTime": "2026-05-21",
                    "arrivalTime": "15:00:00",
                    "checkOutTime": "2026-05-22",
                    "departureTime": "12:00:00",
                    "night": 1,
                    "roomPrice": 4725000,
                    "servicePrice": 0,
                    "totalPrice": 4725000,
                    "payment": 4725000,
                    "balance": 0,
                    "deposit": 0,
                    "note": [],
                    "guestImagepaper": None,
                },
            ]
        },
    },
}


def _reservation(**overrides) -> dict:
    """A CONFIRMED three-night stay. The doc's own samples are both cancelled,
    so nothing in them exercises the path that actually reaches pricing."""
    row = {
        "bookingCode": "004001",
        "referenceCode": "ABC-123",
        "guestName": "Nguyễn Văn A",
        "roomType": "Căn hộ 3 phòng ngủ",
        "roomName": "B - 2",
        "source": "Booking.com",
        "status": "Đã xác nhận",
        "bookDate": "2026-05-01 09:30:00",
        "checkInTime": "2026-05-21",
        "arrivalTime": "15:00:00",
        "checkOutTime": "2026-05-24",
        "departureTime": "12:00:00",
        "night": 3,
        "roomPrice": 4_725_000,
        "servicePrice": 0,
        "totalPrice": 4_725_000,
        "payment": 0,
        "balance": 0,
        "deposit": 0,
        "note": [],
        "guestImagepaper": None,
    }
    row.update(overrides)
    return row


def _payload(*rows: dict) -> dict:
    return {"data": {"type": "reservation", "attributes": {"reservations": list(rows)}}}


CATEGORY_MAP = {"Căn hộ 3 phòng ngủ": "3br", "Holo Ben Thanh - 1 PN": "2br_regular"}


# =========================================================================
# 1. Testing windows — Asia/Ho_Chi_Minh
# =========================================================================


def test_the_confirmed_windows_are_the_two_the_document_states_unambiguously():
    confirmed = [w for w in windows.TESTING_WINDOWS if w.confirmed]
    # `16:00-16:59` names the last INCLUDED minute; `08:00-08:30` names the END
    # INSTANT. Reading both "through end of minute" would make the morning
    # window 31 minutes long, which nothing would specify. Each is therefore
    # read at its NARROWER interpretation: being one minute short never causes
    # a rejected call, being one minute long does.
    assert [(w.start.hour, w.start.minute, w.end.hour, w.end.minute) for w in confirmed] == [
        (8, 0, 8, 29),
        (16, 0, 16, 59),
    ]


def test_the_midnight_window_is_carried_but_marked_unconfirmed():
    """`24:00-24:59` is not clock notation. It is preserved, never trusted."""
    unconfirmed = [w for w in windows.TESTING_WINDOWS if not w.confirmed]
    assert len(unconfirmed) == 1, "the document has exactly one ambiguous window"


def test_a_time_inside_the_morning_window_reports_open():
    status = windows.window_status(datetime(2026, 5, 21, 8, 15, tzinfo=VN))
    assert status.is_open is True


def test_the_end_minute_of_a_window_is_still_inside_it():
    """`16:00-16:59` names the whole 16:00 hour, so 16:59:59 is in."""
    assert windows.window_status(datetime(2026, 5, 21, 16, 59, 59, tzinfo=VN)).is_open is True


def test_one_second_after_a_window_reports_closed():
    assert windows.window_status(datetime(2026, 5, 21, 17, 0, 0, tzinfo=VN)).is_open is False


def test_the_unconfirmed_midnight_window_never_reports_open():
    """Auto-firing calls on a guess about `24:00` is exactly what must not happen."""
    for hour, minute in ((0, 30), (23, 59)):
        moment = datetime(2026, 5, 21, hour, minute, tzinfo=VN)
        assert windows.window_status(moment).is_open is False, f"{hour}:{minute} must not be open"


def test_a_utc_instant_is_judged_in_vietnam_time():
    """01:15 UTC is 08:15 in Ho Chi Minh City — inside the morning window."""
    moment = datetime(2026, 5, 21, 1, 15, tzinfo=ZoneInfo("UTC"))
    assert windows.window_status(moment).is_open is True


def test_a_naive_datetime_is_rejected_rather_than_assumed():
    """Guessing the zone of a naive datetime is how an out-of-window call happens."""
    with pytest.raises(ValueError):
        windows.window_status(datetime(2026, 5, 21, 8, 15))


def test_the_next_opening_after_the_morning_window_is_the_afternoon_one():
    status = windows.window_status(datetime(2026, 5, 21, 8, 45, tzinfo=VN))
    assert status.next_open_at == datetime(2026, 5, 21, 16, 0, tzinfo=VN)


def test_the_next_opening_after_the_last_window_rolls_to_tomorrow_morning():
    status = windows.window_status(datetime(2026, 5, 21, 20, 0, tzinfo=VN))
    assert status.next_open_at == datetime(2026, 5, 22, 8, 0, tzinfo=VN)


# =========================================================================
# 2. Reservations -> unit-nights
# =========================================================================


def test_a_three_night_stay_becomes_three_unit_night_rows():
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert [b.stay_date for b in out] == [date(2026, 5, 21), date(2026, 5, 22), date(2026, 5, 23)]


def test_the_checkout_date_is_not_an_occupied_night():
    """The guest leaves on checkOutTime. Counting it inflates every occupancy."""
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert date(2026, 5, 24) not in {b.stay_date for b in out}


def test_every_emitted_row_carries_nights_equal_to_one():
    """A Booking row is ONE OCCUPIED UNIT-NIGHT (see lib/types.ts, routers/bookings.py).

    Blue Jay's `night` is a real stay length, unlike the mock's decorative one,
    which makes it a trap: copying it onto each expanded row would hand a
    downstream reader a number that looks authoritative and multiplies
    occupancy by the stay length.
    """
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert {b.nights for b in out} == {1}


def test_the_booking_creation_date_survives_normalisation():
    """`bookDate` is the whole reason pickup and booking curves become possible."""
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert {b.booked_at for b in out} == {date(2026, 5, 1)}


def test_the_nightly_rate_is_the_room_price_divided_by_the_nights():
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert {b.net_rate for b in out} == {1_575_000.0}


def test_a_cancelled_reservation_does_not_become_occupancy():
    """Both of the document's own samples are cancelled."""
    out = normalize.reservations_to_bookings(DOC_RESERVATION_PAYLOAD, category_map=CATEGORY_MAP)
    assert out == []


def test_a_lone_unrecognised_status_is_skipped_and_reported_not_fatal():
    """Never counted as confirmed — but one odd record must not cost the other 99%.

    Repetition is what separates a record anomaly from a vocabulary gap, which
    is the same lever `generate_recommendations` already uses.
    """
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(status="Trạng thái mới")),
        category_map=CATEGORY_MAP,
        report=report,
    )
    assert out == []
    assert report.skipped == 1
    assert any("Trạng thái mới" in w for w in report.warnings)


def test_the_same_unknown_status_repeating_is_a_vocabulary_gap_and_raises():
    rows = [_reservation(bookingCode=f"X{i}", status="Trạng thái mới") for i in range(3)]
    with pytest.raises(normalize.UnmappedValue):
        normalize.reservations_to_bookings(_payload(*rows), category_map=CATEGORY_MAP)


def test_an_unknown_status_never_yields_an_occupied_night():
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(status="Trạng thái mới")),
        category_map=CATEGORY_MAP,
        report=report,
    )
    assert normalize.units_sold_by_date(out) == {}


def test_an_unmapped_room_type_raises_rather_than_being_guessed():
    with pytest.raises(normalize.UnmappedValue):
        normalize.reservations_to_bookings(
            _payload(_reservation(roomType="Phòng lạ")), category_map=CATEGORY_MAP
        )


def test_the_stay_length_is_taken_from_the_dates_not_the_night_count():
    """Dates are unambiguous; a count can disagree with them. When they differ
    the dates win and the disagreement is reported, never silently resolved."""
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(night=9)), category_map=CATEGORY_MAP, report=report
    )
    assert len(out) == 3
    assert report.discrepancies, "a night-count mismatch must be reported"


def test_a_missing_checkout_falls_back_to_the_night_count():
    out = normalize.reservations_to_bookings(
        _payload(_reservation(checkOutTime=None, night=2)), category_map=CATEGORY_MAP
    )
    assert [b.stay_date for b in out] == [date(2026, 5, 21), date(2026, 5, 22)]


def test_the_booking_source_is_carried_through_as_the_channel():
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert {b.channel for b in out} == {"Booking.com"}


def test_expanded_rows_from_one_reservation_get_distinct_external_ids():
    """They land in one table keyed by external_id; a shared id collapses a stay
    into a single night."""
    out = normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP
    )
    assert len({b.external_id for b in out}) == 3


# =========================================================================
# 3. Derived occupancy and ADR (one endpoint, three signals)
# =========================================================================


def test_units_sold_is_counted_from_the_expanded_unit_nights():
    rows = normalize.reservations_to_bookings(
        _payload(
            _reservation(bookingCode="A", checkInTime="2026-05-21", checkOutTime="2026-05-22", night=1),
            _reservation(bookingCode="B", checkInTime="2026-05-21", checkOutTime="2026-05-22", night=1),
        ),
        category_map=CATEGORY_MAP,
    )
    sold = normalize.units_sold_by_date(rows)
    assert sold[("3br", date(2026, 5, 21))] == 2


def test_the_derived_rate_is_the_mean_nightly_rate_actually_booked():
    rows = normalize.reservations_to_bookings(
        _payload(
            _reservation(bookingCode="A", roomPrice=3_000_000, night=1, checkOutTime="2026-05-22"),
            _reservation(bookingCode="B", roomPrice=1_000_000, night=1, checkOutTime="2026-05-22"),
        ),
        category_map=CATEGORY_MAP,
    )
    adr = normalize.derive_adr(rows)
    assert adr[("3br", date(2026, 5, 21))] == 2_000_000.0


def test_a_date_with_no_bookings_has_no_derived_rate():
    """The hole in ADR-from-reservations: empty future dates yield nothing, and
    those are exactly the dates pricing most wants to move. The caller must
    fall back explicitly rather than read a zero as a rate."""
    adr = normalize.derive_adr([])
    assert adr == {}


def test_a_derived_rate_records_that_it_was_derived_not_published():
    """Blue Jay publishes no forward rate. A realized ADR standing in for one
    must say so, or the operator reads an achieved average as a list price."""
    inv = normalize.build_inventory(
        stay_dates=[date(2026, 5, 21)],
        categories=["3br"],
        units_total={"3br": 4},
        units_sold={("3br", date(2026, 5, 21)): 2},
        adr={("3br", date(2026, 5, 21)): 2_000_000.0},
        fallback_rate={"3br": 3_800_000.0},
    )
    assert inv[0].rate_provenance == "derived_adr"


def test_a_date_without_an_adr_falls_back_and_says_so():
    inv = normalize.build_inventory(
        stay_dates=[date(2026, 5, 21)],
        categories=["3br"],
        units_total={"3br": 4},
        units_sold={},
        adr={},
        # Keyed by (category, DATE): the seasonal band a night belongs to is a
        # property of that night, not of the window it happens to sit in.
        fallback_rate={("3br", date(2026, 5, 21)): 3_800_000.0},
    )
    assert inv[0].rate_provenance == "seasonal_base"
    assert inv[0].current_net_rate == 3_800_000.0


# =========================================================================
# 4. Room types and units — the U11 unblock
# =========================================================================


def test_units_total_is_the_count_of_physical_rooms_in_that_room_type():
    """ASSUMPTIONS U11, the hard blocker: occupancy is per room type, so the
    unit split has to be real rather than the seeded 10/8/4 guess."""
    room_types = [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}]
    rooms = [
        {"roomdetailId": 1, "roomtypeId": 6153, "roomName": "B - 1"},
        {"roomdetailId": 2, "roomtypeId": 6153, "roomName": "B - 2"},
        {"roomdetailId": 3, "roomtypeId": 6153, "roomName": "B - 3"},
    ]
    out = normalize.room_types_to_dtos(
        room_types, rooms, category_map=CATEGORY_MAP, property_external_id="1003"
    )
    assert out[0].units_total == 3


def test_a_room_type_with_no_units_is_reported_rather_than_priced():
    room_types = [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}]
    report = normalize.NormalisationReport()
    normalize.room_types_to_dtos(
        room_types, [], category_map=CATEGORY_MAP, property_external_id="1003", report=report
    )
    assert report.warnings, "zero units breaks occupancy and must not pass silently"


# =========================================================================
# 5. Occupancy report — cross-check only, and a dd/mm trap
# =========================================================================


def test_the_occupancy_report_date_is_read_as_day_first():
    """`01/06/2026` in a Vietnamese report is 1 June, not 6 January. Reading it
    the other way silently shifts an entire report by months."""
    parsed = normalize.parse_report_date("01/06/2026")
    assert parsed == date(2026, 6, 1)


def test_the_documented_occupancy_sample_fails_its_own_arithmetic():
    """TotalRoom 3003 - RoomOccupied 73 - Blocked 0 = 2930, but the document
    says RoomEmpty is 2970. Pinned so the live response is checked against
    arithmetic rather than against the document."""
    daily = {"Date": "01/06/2026", "RoomOccupied": 73, "Blocked": 0, "TotalRoom": 3003, "RoomEmpty": 2970}
    assert normalize.occupancy_row_is_consistent(daily) is False


def test_a_self_consistent_occupancy_row_passes_the_check():
    daily = {"Date": "01/06/2026", "RoomOccupied": 20, "Blocked": 3, "TotalRoom": 30, "RoomEmpty": 7}
    assert normalize.occupancy_row_is_consistent(daily) is True


# =========================================================================
# 6. PII sanitisation — allowlist, not denylist
# =========================================================================

PII_FIELDS = ("guestName", "guestImagepaper", "note", "referenceCode", "payment", "balance", "deposit")


@pytest.mark.parametrize("field", PII_FIELDS)
def test_no_personal_or_financial_field_survives_sanitisation(field):
    clean = sanitize.sanitize_reservations(DOC_RESERVATION_PAYLOAD)
    blob = repr(clean)
    assert field not in blob


def test_the_guest_name_value_is_gone_not_just_its_key():
    clean = sanitize.sanitize_reservations(DOC_RESERVATION_PAYLOAD)
    assert "Ghép đoàn Hà test" not in repr(clean)


def test_sanitisation_keeps_every_field_pricing_actually_needs():
    clean = sanitize.sanitize_reservations(_payload(_reservation()))
    kept = clean["data"]["attributes"]["reservations"][0]
    for needed in ("roomType", "status", "bookDate", "checkInTime", "checkOutTime", "night", "roomPrice", "source"):
        assert needed in kept, f"{needed} is required downstream"


def test_the_booking_code_becomes_a_stable_pseudonym():
    """Rows must stay linkable across a capture without carrying the real code."""
    first = sanitize.sanitize_reservations(_payload(_reservation()))
    second = sanitize.sanitize_reservations(_payload(_reservation()))
    code = first["data"]["attributes"]["reservations"][0]["bookingCode"]
    assert code != "004001"
    assert code == second["data"]["attributes"]["reservations"][0]["bookingCode"]


def test_sanitisation_is_an_allowlist_so_a_new_vendor_field_cannot_leak():
    """A denylist ships the next field Blue Jay adds. This must fail closed."""
    clean = sanitize.sanitize_reservations(
        _payload(_reservation(guestPassportNumber="B1234567", guestPhone="+84900000000"))
    )
    blob = repr(clean)
    assert "B1234567" not in blob
    assert "+84900000000" not in blob


# =========================================================================
# 7. Malformed vendor rows degrade, they do not take the sync down
# =========================================================================


def test_a_non_numeric_night_count_does_not_crash_the_whole_sync():
    """One bad row out of hundreds must not cost the operator the other rows.

    `int("abc")` raises, and the reservation list is fetched as one page, so an
    unguarded cast turns a single malformed record into a total sync failure.
    """
    out = normalize.reservations_to_bookings(
        _payload(_reservation(night="abc")), category_map=CATEGORY_MAP
    )
    assert [b.stay_date for b in out] == [date(2026, 5, 21), date(2026, 5, 22), date(2026, 5, 23)]


def test_a_null_room_price_yields_a_zero_rate_rather_than_raising():
    out = normalize.reservations_to_bookings(
        _payload(_reservation(roomPrice=None)), category_map=CATEGORY_MAP
    )
    assert {b.net_rate for b in out} == {0.0}


def test_a_reservation_covering_no_nights_is_skipped_and_counted():
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(checkInTime="2026-05-21", checkOutTime="2026-05-21", night=0)),
        category_map=CATEGORY_MAP,
        report=report,
    )
    assert out == []
    assert report.skipped == 1


def test_an_occupancy_row_with_a_non_numeric_field_is_reported_inconsistent():
    assert normalize.occupancy_row_is_consistent(
        {"TotalRoom": "n/a", "RoomOccupied": 1, "Blocked": 0, "RoomEmpty": 1}
    ) is False


def test_a_reservation_missing_a_checkin_date_is_skipped_with_a_warning():
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(checkInTime=None)), category_map=CATEGORY_MAP, report=report
    )
    assert out == []
    assert report.warnings


# =========================================================================
# 8. Review findings — slice 1
# =========================================================================


def test_a_malformed_date_skips_its_row_without_losing_the_others():
    """`dd/mm/yyyy` is not hypothetical: the occupancy report on this same API
    uses it, so a reservation payload drifting to it is a realistic change.
    Numbers already degrade here; dates must too."""
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(
            _reservation(bookingCode="GOOD"),
            _reservation(bookingCode="BAD", checkInTime="01/06/2026"),
        ),
        category_map=CATEGORY_MAP,
        report=report,
    )
    assert {b.external_id.split(":")[0] for b in out} == {"GOOD"}
    assert report.warnings


def test_the_pseudonym_salt_can_be_supplied_out_of_band(monkeypatch):
    """A fixed salt in a PUBLIC repo plus 6-digit booking codes is a rainbow
    table, so the in-source value cannot be the one protecting a snapshot."""
    monkeypatch.setenv("BLUEJAY_PSEUDONYM_SALT", "a-private-salt")
    private = sanitize.pseudonymise("003283")
    monkeypatch.delenv("BLUEJAY_PSEUDONYM_SALT")
    assert private != sanitize.pseudonymise("003283")


def test_the_category_map_is_keyed_by_room_type_id_so_a_rename_cannot_break_it():
    """Blue Jay HAS room-type ids — the reservation filter accepts them. Only
    the reservation OUTPUT is name-only, and those names are editable."""
    room_types = [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ ĐÃ ĐỔI TÊN"}]
    resolved = normalize.build_name_category_map(room_types, {"6153": "3br"})
    assert resolved == {"Căn hộ 3 phòng ngủ ĐÃ ĐỔI TÊN": "3br"}


def test_a_room_type_id_with_no_mapping_is_listed_for_the_operator():
    unmapped = normalize.unmapped_room_type_ids(
        [{"roomtypeId": 6153, "roomtypeName": "Phòng lạ"}], {"9999": "3br"}
    )
    assert unmapped == [("6153", "Phòng lạ")]


def test_a_category_with_no_rate_from_any_source_is_marked_unavailable():
    """Three named sources, four outcomes: the fourth must not borrow the
    third's label. A 0.0 rate labelled `seasonal_base` claims a seasonal base
    supplied it when nothing did."""
    inv = normalize.build_inventory(
        stay_dates=[date(2026, 5, 21)],
        categories=["3br"],
        units_total={"3br": 4},
        units_sold={},
        adr={},
        fallback_rate={},
    )
    assert inv[0].rate_provenance == "unavailable"


def test_a_tentative_hold_does_not_occupy_a_room():
    """`đã đặt` (booked) and `giữ chỗ` (holding a place) both map to vendor code
    1, but only one is real occupancy. Counting a hold inflates occupancy,
    which inflates pace, which pushes prices UP on dates that are not filling."""
    report = normalize.NormalisationReport()
    out = normalize.reservations_to_bookings(
        _payload(_reservation(status="Giữ chỗ")), category_map=CATEGORY_MAP, report=report
    )
    assert out == []


def test_a_firm_booking_does_occupy_a_room():
    out = normalize.reservations_to_bookings(
        _payload(_reservation(status="Đã đặt")), category_map=CATEGORY_MAP
    )
    assert len(out) == 3


def test_reservations_missing_a_booking_code_stay_distinguishable():
    out = normalize.reservations_to_bookings(
        _payload(
            _reservation(bookingCode="", checkOutTime="2026-05-22", night=1),
            _reservation(bookingCode=None, checkOutTime="2026-05-22", night=1),
        ),
        category_map=CATEGORY_MAP,
    )
    assert len({b.external_id for b in out}) == 2


def test_the_occupancy_grand_total_satisfies_the_vendors_own_invariant():
    """POSITIVE evidence that `total - occupied - blocked == empty` is what Blue
    Jay means. Only the detail rows in the sample are placeholder."""
    grand = {"TotalRoom": 30849, "RoomOccupied": 781, "Blocked": 36, "RoomEmpty": 30032}
    assert normalize.occupancy_row_is_consistent(grand) is True


def test_unparseable_and_inconsistent_occupancy_rows_are_told_apart():
    """"Vendor arithmetic is wrong" and "vendor sent junk" warrant different
    conversations with Blue Jay."""
    assert normalize.occupancy_row_problem(
        {"TotalRoom": "n/a", "RoomOccupied": 1, "Blocked": 0, "RoomEmpty": 1}
    ) == "unparseable"
    assert normalize.occupancy_row_problem(
        {"TotalRoom": 3003, "RoomOccupied": 73, "Blocked": 0, "RoomEmpty": 2970}
    ) == "inconsistent"
    assert normalize.occupancy_row_problem(
        {"TotalRoom": 30, "RoomOccupied": 20, "Blocked": 3, "RoomEmpty": 7}
    ) is None


# =========================================================================
# 9. Review round 2 — the vendor sends something the document did not describe
#
# Theme: every one of these degraded SILENTLY and in the direction of a wrong
# pricing decision. The rule that closes them as a class is that a fallback to
# a default must always leave a trace in the NormalisationReport.
# =========================================================================


def test_an_error_envelope_is_never_read_as_an_empty_hotel():
    """The worst failure in the adapter.

    Zero bookings is not a neutral answer: it means 0% occupancy on every date
    in the horizon, which is the strongest DISCOUNT signal the engine has. A
    revoked key, a quota refusal or a shape change must never render as
    "price everything down as hard as the bounds allow".
    """
    with pytest.raises(normalize.VendorPayloadError):
        normalize.reservations_to_bookings(
            {"status": "error", "message": "Invalid API key"}, category_map=CATEGORY_MAP
        )


def test_an_unrecognisable_payload_shape_raises_rather_than_returning_nothing():
    for payload in ({}, {"data": {}}, {"data": {"attributes": {}}}, {"unexpected": 1}):
        with pytest.raises(normalize.VendorPayloadError):
            normalize.reservations_to_bookings(payload, category_map=CATEGORY_MAP)


def test_a_genuinely_empty_period_is_still_allowed_to_be_empty():
    """The distinction only has value if a real zero still passes."""
    payload = {"data": {"type": "reservation", "attributes": {"reservations": []}}}
    assert normalize.reservations_to_bookings(payload, category_map=CATEGORY_MAP) == []


def test_a_success_envelope_with_no_rows_is_empty_not_an_error():
    payload = {
        "status": "success",
        "message": "ok",
        "data": {"type": "reservation", "attributes": {"reservations": []}},
    }
    assert normalize.reservations_to_bookings(payload, category_map=CATEGORY_MAP) == []


def test_a_multi_night_stay_flags_that_the_room_price_basis_is_unverified():
    """Both documented samples are `night: 1`, where a stay total and a nightly
    rate are the SAME NUMBER — so the document provides no evidence for which
    `roomPrice` is. It drives change_pct, i.e. the calendar's change column and
    the bigChange attention threshold."""
    report = normalize.NormalisationReport()
    normalize.reservations_to_bookings(
        _payload(_reservation()), category_map=CATEGORY_MAP, report=report
    )
    assert any("roomPrice" in d for d in report.discrepancies)


def test_a_single_night_stay_needs_no_room_price_caveat():
    report = normalize.NormalisationReport()
    normalize.reservations_to_bookings(
        _payload(_reservation(checkOutTime="2026-05-22", night=1)),
        category_map=CATEGORY_MAP,
        report=report,
    )
    assert not any("roomPrice" in d for d in report.discrepancies)


def test_a_decomposed_unicode_room_type_matches_its_composed_mapping():
    """NFD and NFC forms of the same Vietnamese text are visually identical and
    byte-different. Pasting a mapping from a macOS-originated source would
    otherwise raise UnmappedValue naming a room type already mapped."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "Căn hộ 3 phòng ngủ")
    assert decomposed != "Căn hộ 3 phòng ngủ"
    out = normalize.reservations_to_bookings(
        _payload(_reservation(roomType=decomposed)), category_map=CATEGORY_MAP
    )
    assert len(out) == 3


def test_a_decomposed_unicode_status_still_resolves():
    import unicodedata

    out = normalize.reservations_to_bookings(
        _payload(_reservation(status=unicodedata.normalize("NFD", "Đã xác nhận"))),
        category_map=CATEGORY_MAP,
    )
    assert len(out) == 3


def test_a_malformed_night_count_leaves_a_trace_in_the_report():
    """`_as_int("abc")` returns 0, which is falsy, so the discrepancy branch
    never fired and the module's own "every disagreement is reported" promise
    was quietly broken."""
    report = normalize.NormalisationReport()
    normalize.reservations_to_bookings(
        _payload(_reservation(night="abc")), category_map=CATEGORY_MAP, report=report
    )
    assert report.warnings or report.discrepancies


def test_two_rooms_on_one_booking_code_get_distinct_row_ids():
    """One reservation code can cover several physical rooms. Without the unit
    in the key they collide, which becomes data loss the moment anything
    upserts on external_id."""
    out = normalize.reservations_to_bookings(
        _payload(
            _reservation(bookingCode="SAME", roomName="B - 1", checkOutTime="2026-05-22", night=1),
            _reservation(bookingCode="SAME", roomName="B - 2", checkOutTime="2026-05-22", night=1),
        ),
        category_map=CATEGORY_MAP,
    )
    assert len({b.external_id for b in out}) == 2


def test_a_physical_room_pointing_at_an_unknown_room_type_is_reported():
    """It vanishes from units_total, so occupancy = sold/total is OVERSTATED and
    the engine recommends higher prices than warranted. Direction matters."""
    report = normalize.NormalisationReport()
    normalize.room_types_to_dtos(
        [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}],
        [{"roomdetailId": 1, "roomtypeId": 9999, "roomName": "X - 1"}],
        category_map=CATEGORY_MAP,
        property_external_id="1003",
        report=report,
    )
    assert any("9999" in w for w in report.warnings)


def test_an_all_zero_occupancy_row_of_junk_is_not_certified_as_sound():
    """`_as_int` coerced everything unparseable to 0, and 0-0-0 == 0, so the
    cross-check handed a clean bill of health to unreadable data — the one
    verdict it must never produce."""
    assert normalize.occupancy_row_problem(
        {"TotalRoom": "n/a", "RoomOccupied": None, "Blocked": "", "RoomEmpty": None}
    ) == "unparseable"


def test_the_sanitiser_keeps_whatever_spelling_the_parser_accepts():
    """A snapshot that parses differently from a live response stops being
    evidence about the live one. Worst case an all-lowercase row sanitises to
    {} and units_total goes to zero for every category."""
    rows = [{"roomdetailid": 1, "roomtypeid": 6153, "roomname": "B - 1"}]
    cleaned = sanitize.sanitize_rows(rows, sanitize.ROOM_DETAIL_ALLOWLIST)
    assert cleaned and cleaned[0], "case-different keys must survive sanitisation"
    assert normalize.room_types_to_dtos(
        [{"roomtypeId": 6153, "roomtypeName": "Căn hộ 3 phòng ngủ"}],
        cleaned,
        category_map=CATEGORY_MAP,
        property_external_id="1003",
    )[0].units_total == 1


# =========================================================================
# 10. Review round 3 — the snapshot path bypassed the envelope check
# =========================================================================


def test_sanitising_does_not_launder_an_error_envelope_into_an_empty_hotel():
    """The envelope check was verified on the LIVE path only.

    Sanitisation dropped `status`/`message` (they are not in the allowlist) and
    coerced a null `data` to `{}`, so an error response became a STRUCTURALLY
    VALID snapshot asserting 0% occupancy on every date. That is worse than the
    bug it descends from: the live version failed once, a snapshot is a file
    that keeps lying every time it replays.
    """
    laundered = sanitize.sanitize_reservations(
        {"status": "error", "message": "Invalid API key", "data": None}
    )
    with pytest.raises(normalize.VendorPayloadError):
        normalize.reservations_to_bookings(laundered, category_map=CATEGORY_MAP)


def test_the_vendor_message_survives_sanitisation_because_it_is_the_cause():
    """`message` is vendor prose about the request, not about a guest. It is
    the field that says WHY, so a snapshot recording "this capture failed" is
    more useful than one that silently cannot exist."""
    clean = sanitize.sanitize_reservations(
        {"status": "error", "message": "Invalid API key", "data": None}
    )
    assert clean.get("status") == "error"
    assert "Invalid API key" in repr(clean)


def test_a_successful_envelope_still_sanitises_normally():
    clean = sanitize.sanitize_reservations(
        {"status": "success", "message": "ok", "data": DOC_RESERVATION_PAYLOAD["data"]}
    )
    assert clean["data"]["attributes"]["reservations"]
    assert "Ghép đoàn Hà test" not in repr(clean)


def test_every_field_spelling_the_parser_accepts_is_also_allowlisted():
    """Audited as a PAIR, not field by field.

    A spelling `_first` accepts but the allowlist drops means the live path
    parses and the snapshot does not — `roomtype_id` was exactly that, and
    case-insensitive matching does not fold an underscore. The failure is
    silent: every room collapses under an empty key and units_total goes to 0.
    """
    room_detail_spellings = {"roomdetailId", "roomDetailId", "roomtype_id", "roomtypeId", "roomTypeId", "roomName", "name"}
    allowed = {k.lower() for k in sanitize.ROOM_DETAIL_ALLOWLIST}
    missing = sorted(s for s in room_detail_spellings if s.lower() not in allowed)
    assert not missing, f"parser accepts these but the sanitiser drops them: {missing}"


# =========================================================================
# 11. Review round 4 — every value the backend can emit needs a rendering
# =========================================================================


def test_build_inventory_only_ever_emits_a_declared_provenance():
    """The set has to have ONE definition, or the UI is matching against a
    guess about what the backend produces."""
    from dynamic_pricing.providers.pms.base import RATE_PROVENANCE_VALUES

    inv = normalize.build_inventory(
        stay_dates=[date(2026, 5, 21), date(2026, 5, 22)],
        categories=["3br"],
        units_total={"3br": 4},
        units_sold={},
        adr={("3br", date(2026, 5, 21)): 2_000_000.0},
        fallback_rate={("3br", date(2026, 5, 22)): 3_800_000.0},
    )
    assert {row.rate_provenance for row in inv} <= set(RATE_PROVENANCE_VALUES)


def test_the_seasonal_base_fallback_uses_the_band_for_THAT_date():
    """D17: the season SELECTS the band. Looking the band up once at the window
    start and applying it across the whole horizon stretches one season's band
    over three — which is the double-counting D17 exists to forbid, arriving
    from the opposite direction.

    And per the empty-date chain, `seasonal_base` is the provenance for every
    unbooked night, so this is the value MOST far-out dates get.
    """
    high_1 = date(2026, 8, 27)   # High Season 1
    low_2 = date(2026, 9, 26)    # Low Season 2 — a different band
    inv = normalize.build_inventory(
        stay_dates=[high_1, low_2],
        categories=["2br_regular"],
        units_total={"2br_regular": 10},
        units_sold={},
        adr={},
        fallback_rate={
            ("2br_regular", high_1): 2_300_000.0,
            ("2br_regular", low_2): 2_100_000.0,
        },
    )
    by_date = {row.stay_date: row.current_net_rate for row in inv}
    assert by_date[high_1] == 2_300_000.0
    assert by_date[low_2] == 2_100_000.0
