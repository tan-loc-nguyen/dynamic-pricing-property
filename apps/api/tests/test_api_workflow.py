"""End-to-end: seed -> recommend -> accept/override -> history -> outcomes.

Runs against a throwaway SQLite file so it never touches the demo database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"
os.environ["DATA_PROVIDER"] = "mock"
os.environ["MARKET_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from dynamic_pricing.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# NOTE ON ORDERING: these tests share one module-scoped client and database, and
# several are destructive -- saving a config with regenerate=true replaces the
# whole run, so any recommendation id captured before it is stale afterwards.
# Every test therefore fetches the rows it needs at its own start rather than
# relying on ids from an earlier test, and any test that replaces a run restores
# the configuration before returning. Do not introduce a test that captures ids
# and then regenerates.


# ------------------------------------------------------------------- system
def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_data_is_seeded_on_startup(client):
    counts = client.get("/api/status").json()["counts"]
    assert counts["room_types"] == 3
    assert counts["physical_rooms"] == 22, "the client operates 22 apartments"
    assert counts["rate_bands"] == 15
    assert counts["recommendations_all_runs"] > 100
    assert counts["events"] > 0
    assert counts["competitors"] > 0


def test_shadow_mode_is_the_default(client):
    status = client.get("/api/status").json()
    assert status["mode"] == "shadow"
    assert client.get("/api/recommendations/summary").json()["mode"] == "shadow"


def test_status_separates_validated_from_unvalidated(client):
    status = client.get("/api/status").json()
    assert status["rate_book"]["source"] == "CLIENT_VALIDATED"
    assert status["rate_book"]["rate_basis"] == "NET"
    assert status["booking_curve"]["validated"] is False
    assert "NOT Luminous data" in status["booking_curve"]["note"]


def test_the_engine_registry_is_the_pluggability_seam(client):
    """One engine today. The registry exists so a finance-authored engine can
    replace it without touching the UI, database, providers or history."""
    engines = client.get("/api/engines").json()
    assert [e["key"] for e in engines] == ["default"]
    assert engines[0]["version"]


# ---------------------------------------------------------------- rate book
def test_rate_book_exposes_all_fifteen_validated_bands(client):
    bands = client.get("/api/rate-book").json()
    assert len(bands) == 15
    assert all(b["rate_basis"] == "NET" for b in bands)
    assert all(b["source"] == "CLIENT_VALIDATED" for b in bands)

    high2_3br = next(
        b for b in bands if b["season_key"] == "high_2" and b["room_category"] == "3br"
    )
    assert (high2_3br["min_net_rate"], high2_3br["base_net_rate"], high2_3br["max_net_rate"]) == (
        3_200_000, 3_800_000, 4_300_000,
    )
    assert 1 in high2_3br["months"], "January belongs to the Nov-Jan high season"


def test_rate_book_edit_is_marked_as_operator_edited(client):
    band = client.get("/api/rate-book").json()[0]
    updated = client.put(
        f"/api/rate-book/{band['id']}",
        json={
            "min_net_rate": band["min_net_rate"],
            "base_net_rate": band["base_net_rate"] + 100_000,
            "max_net_rate": band["max_net_rate"],
        },
    ).json()
    assert updated["source"] == "OPERATOR_EDITED"

    client.post("/api/rate-book/reset")
    restored = next(b for b in client.get("/api/rate-book").json() if b["id"] == band["id"])
    assert restored["source"] == "CLIENT_VALIDATED"
    assert restored["base_net_rate"] == band["base_net_rate"]


def test_rate_band_rejects_inverted_bounds(client):
    band = client.get("/api/rate-book").json()[0]
    response = client.put(
        f"/api/rate-book/{band['id']}",
        json={"min_net_rate": 5_000_000, "base_net_rate": 2_000_000, "max_net_rate": 1_000_000},
    )
    assert response.status_code == 422


# ----------------------------------------------------------- recommendations
def test_recommendations_are_room_type_by_stay_date(client):
    recs = client.get("/api/recommendations?limit=2000").json()
    assert recs
    keys = [(r["room_type_id"], r["stay_date"]) for r in recs]
    assert len(keys) == len(set(keys)), "one recommendation per room type per stay date"
    assert {r["room_category"] for r in recs} == {"2br_regular", "2br_premium", "3br"}


def test_recommendations_are_anchored_to_the_validated_band(client):
    for rec in client.get("/api/recommendations?limit=200").json():
        assert rec["band_min_net_rate"] <= rec["recommended_net_rate"] <= rec["band_max_net_rate"]
        assert rec["base_net_rate"] == rec["band_base_net_rate"]
        assert rec["rate_band_source"] == "CLIENT_VALIDATED"


def test_recommendations_are_varied(client):
    recs = client.get("/api/recommendations?limit=2000").json()
    assert len({r["recommended_net_rate"] for r in recs}) > 20
    adjustments = [r["total_adjustment_pct"] for r in recs]
    assert max(adjustments) > 0 and min(adjustments) < 0


def test_demo_covers_every_teaching_scenario(client):
    recs = client.get("/api/recommendations?limit=2000").json()
    assert any(r["is_event"] for r in recs), "no event date"
    assert any(r["pace_gap"] is not None and r["pace_gap"] > 0.08 for r in recs), "none ahead of pace"
    assert any(r["pace_gap"] is not None and r["pace_gap"] < -0.08 for r in recs), "none behind pace"
    assert any(r["market_observation_count"] == 0 for r in recs), "no missing-market date"
    assert any(r["market_ignored_count"] > 0 for r in recs), "no low-confidence-market date"
    assert any(r["clamp_applied"] == "min" for r in recs), "no MIN clamp"
    assert any(r["clamp_applied"] == "max" for r in recs), "no MAX clamp"
    assert len({r["season_key"] for r in recs}) >= 2, "horizon should cross a season boundary"


def test_every_recommendation_is_explainable(client):
    for rec in client.get("/api/recommendations?limit=25").json():
        detail = client.get(f"/api/recommendations/{rec['id']}").json()
        assert detail["adjustments"], "recommendation with no breakdown"
        assert detail["adjustments"][0]["code"] == "rate_band", "band must be shown first"
        for adj in detail["adjustments"]:
            # Either a translatable key, or operator-authored wording to show
            # verbatim -- a step with neither renders as a blank line.
            assert adj["label_key"] or adj["label"], f"unlabelled step: {adj['code']}"
            assert isinstance(adj["params"], dict)
        running = detail["base_net_rate"]
        for adj in detail["adjustments"]:
            assert adj["price_before"] == pytest.approx(running, abs=0.02)
            running = adj["price_after"]
        assert detail["recommended_net_rate"] == pytest.approx(running, abs=0.02)


def test_recommendation_snapshot_is_reproducible(client):
    rec = client.get("/api/recommendations?limit=1").json()[0]
    detail = client.get(f"/api/recommendations/{rec['id']}").json()
    features = detail["features"]
    for key in (
        "band_base_net_rate", "band_min_net_rate", "band_max_net_rate", "season_key",
        "occupancy", "expected_occupancy", "pace_gap", "days_to_arrival", "rate_band_source",
    ):
        assert key in features, f"snapshot missing {key}"
    assert detail["metadata"]["rate_band_status"] == "CLIENT_VALIDATED"
    assert detail["metadata"]["dynamic_assumptions_status"] == "UNVALIDATED"


def test_no_seasonality_factor_in_any_breakdown(client):
    for rec in client.get("/api/recommendations?limit=40").json():
        codes = {a["code"] for a in client.get(f"/api/recommendations/{rec['id']}").json()["adjustments"]}
        assert "season" not in codes and "seasonality" not in codes


# ------------------------------------------------------------ human decisions
def test_accept_persists_a_decision_and_applies_the_net_rate(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    result = client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "ok"}).json()
    assert result["status"] == "accepted"
    decision = result["decisions"][0]
    assert decision["final_net_rate"] == rec["recommended_net_rate"]
    assert decision["previous_net_rate"] == rec["current_net_rate"]
    assert decision["engine_version"] and decision["config_version"]


def test_override_persists_rate_reason_and_note(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    result = client.post(
        f"/api/recommendations/{rec['id']}/override",
        json={"final_net_rate": 2_222_000, "reason_code": "owner_constraint", "note": "owner floor"},
    ).json()
    assert result["status"] == "overridden"
    decision = result["decisions"][0]
    assert decision["final_net_rate"] == 2_222_000
    assert decision["reason_label"] == "Owner constraint"
    assert decision["note"] == "owner floor"


def test_override_rejects_an_unknown_reason(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    response = client.post(
        f"/api/recommendations/{rec['id']}/override",
        json={"final_net_rate": 2_000_000, "reason_code": "made_up"},
    )
    assert response.status_code == 422


def test_history_shows_both_decisions(client):
    history = client.get("/api/history").json()
    assert {"accepted", "overridden"} <= {h["decision"] for h in history}
    override = next(h for h in history if h["decision"] == "overridden")
    assert override["reason_label"] and override["season_label"]
    assert override["recommended_net_rate"] and override["final_net_rate"]


def test_recalculating_does_not_duplicate_decision_history(client):
    """Regression: decisions used to be cloned onto each new run."""
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "audit"})
    before = len(client.get("/api/history?limit=1000").json())
    for _ in range(3):
        client.post("/api/recommendations/generate")
    assert len(client.get("/api/history?limit=1000").json()) == before


# ------------------------------------------------------------------ settings
def test_settings_expose_only_the_experimental_layer(client):
    payload = client.get("/api/settings/config").json()["payload"]
    assert "pace" in payload and "recent_pickup" in payload and "market" in payload
    # the validated rate book must NOT be mixed into the experimental config
    assert "rate_book" not in payload
    assert "seasonal_rates" not in payload
    defaults = client.get("/api/settings/defaults").json()
    assert defaults["status"] == "UNVALIDATED"


def test_changing_settings_changes_recommendations(client):
    config = client.get("/api/settings/config").json()
    before = {
        (r["room_type_id"], r["stay_date"]): r["recommended_net_rate"]
        for r in client.get("/api/recommendations?limit=2000").json()
    }
    payload = config["payload"]
    payload["pace"]["bands"][-1]["adjustment_pct"] = 14.0
    payload["pace"]["bands"][0]["adjustment_pct"] = -14.0
    saved = client.put(
        "/api/settings/config", json={"payload": payload, "label": "test", "regenerate": True}
    ).json()
    assert saved["version"] > config["version"]

    after = {
        (r["room_type_id"], r["stay_date"]): r["recommended_net_rate"]
        for r in client.get("/api/recommendations?limit=2000").json()
    }
    shared = set(before) & set(after)
    assert any(after[k] != before[k] for k in shared), "pace change had no effect"
    client.post("/api/settings/reset")


def test_preview_prices_an_unsaved_configuration(client):
    config = client.get("/api/settings/config").json()["payload"]
    baseline = client.post("/api/settings/preview", json={"payload": config}).json()

    import copy

    edited = copy.deepcopy(config)
    edited["event"]["impact_adjustment_pct"]["medium"] = 40.0
    edited["pace"]["bands"][-1]["adjustment_pct"] = 30.0
    preview = client.post("/api/settings/preview", json={"payload": edited}).json()

    assert preview["band_base_net_rate"] == baseline["band_base_net_rate"]
    # preview must NOT persist
    assert client.get("/api/settings/config").json()["payload"]["pace"]["bands"][-1][
        "adjustment_pct"
    ] != 30.0


# -------------------------------------------------------------------- market
def test_manual_high_confidence_observation_is_usable(client):
    recs = client.get("/api/recommendations?limit=2000").json()
    target = next(r for r in recs if r["market_observation_count"] == 0)
    for i in range(3):
        response = client.post(
            "/api/market/observations",
            json={
                "stay_date": target["stay_date"],
                "competitor_name": f"Manual Comp {i}",
                "observed_price": 2_600_000,
                "room_type_id": target["room_type_id"],
                "room_category": target["room_category"],
                "length_of_stay": 1,
                "guests": 2,
                "price_basis": "NET",
                "tax_inclusion": "EXCLUSIVE",
                "fee_inclusion": "EXCLUSIVE",
                "promotion_status": "NONE",
            },
        )
        assert response.status_code == 201
        assert response.json()["confidence"] == "HIGH"


def test_incomplete_manual_observation_scores_low(client):
    response = client.post(
        "/api/market/observations",
        json={
            "stay_date": "2026-12-01",
            "competitor_name": "Vague Comp",
            "observed_price": 3_000_000,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] == "LOW"
    # The reason is a CODE now, so it can be read in Vietnamese too.
    assert body["confidence_code"] == "not_comparable"
    assert "basis_unknown" in body["confidence_gaps"]


def test_comp_set_is_manageable(client):
    created = client.post(
        "/api/market/competitors",
        json={"name": "New Comparable", "location": "District 2", "comparable_category": "3br"},
    )
    assert created.status_code == 201
    names = {c["name"] for c in client.get("/api/market/competitors").json()}
    assert "New Comparable" in names


def test_public_web_provider_is_capped_at_low_confidence(client):
    providers = {p["key"]: p for p in client.get("/api/market/providers").json()}
    assert providers["public_web"]["max_confidence"] == "LOW"
    assert providers["manual"]["max_confidence"] == "HIGH"


def test_public_collector_fails_gracefully(client):
    result = client.post("/api/market/collect", json={"stay_date": "2026-10-20"}).json()
    assert result["ok"] is False
    assert result["remediation"]


# -------------------------------------------------------------------- events
def test_events_can_be_managed_manually(client):
    created = client.post(
        "/api/events",
        json={
            "name": "Test Conference", "start_date": "2026-10-10", "end_date": "2026-10-12",
            "impact_level": "high", "event_type": "conference",
        },
    )
    assert created.status_code == 201
    event_id = created.json()["id"]

    client.post("/api/recommendations/generate")
    recs = client.get("/api/recommendations?start_date=2026-10-10&end_date=2026-10-12").json()
    assert recs and all(r["is_event"] for r in recs)

    assert client.delete(f"/api/events/{event_id}").status_code == 204


def test_event_rejects_inverted_dates(client):
    response = client.post(
        "/api/events",
        json={"name": "Bad", "start_date": "2026-10-12", "end_date": "2026-10-10"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ outcomes
def test_outcome_tracking_is_ready_and_flags_synthetic_data(client):
    summary = client.get("/api/outcomes/summary").json()
    assert "total_outcomes" in summary
    assert summary["real_outcomes"] == 0, "no real outcomes exist yet"

    # Seeding backfills a historical run so demo outcomes have past
    # recommendations to attach to. Regression: this used to select
    # stay_date < today while recommendations only existed for >= today, so
    # the entire outcome path silently produced nothing.
    assert summary["synthetic_outcomes"] > 0, "demo outcomes were never created"

    created = client.post("/api/outcomes/demo").json()
    assert created["is_synthetic"] is True
    after = client.get("/api/outcomes/summary").json()
    assert after["synthetic_outcomes"] >= summary["synthetic_outcomes"]
    assert after["ready_for_evaluation"] is False, "synthetic data must not count as ready"


def test_real_outcome_can_be_recorded(client):
    rec = client.get("/api/recommendations?limit=1").json()[0]
    created = client.post(
        "/api/outcomes",
        json={
            "recommendation_id": rec["id"], "units_booked": 6, "final_occupancy": 0.6,
            "realized_net_rate": 2_150_000, "source": "bluejay-export",
        },
    ).json()
    assert created["is_synthetic"] is False
    assert created["realized_revenue"] == pytest.approx(2_150_000 * 6)
    assert client.get("/api/outcomes/summary").json()["real_outcomes"] >= 1


# ------------------------------------- regressions: filters before the limit
def test_history_filter_searches_all_decisions_not_just_the_last_page(client):
    """Regression: room_type_id was filtered in Python AFTER the SQL limit, so a
    room type with only older activity looked like it had none."""
    recs = client.get("/api/recommendations?limit=2000").json()
    target = next(r for r in recs if r["room_category"] == "3br")
    client.post(
        f"/api/recommendations/{target['id']}/override",
        json={"final_net_rate": 3_333_000, "reason_code": "promotion", "note": "oldest"},
    )
    # bury it under newer decisions
    for rec in [r for r in recs if r["room_category"] != "3br"][:12]:
        client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "filler"})

    filtered = client.get(
        f"/api/history?room_type_id={target['room_type_id']}&limit=5"
    ).json()
    assert filtered, "filtering by room type must search all decisions, not one page"
    assert all(h["room_category_label"] == target["room_category_label"] for h in filtered)


def test_room_category_filter_is_applied_before_paging(client):
    """Regression: category filtered an already-truncated page."""
    page = client.get("/api/recommendations?room_category=3br&limit=10").json()
    assert len(page) == 10, "a filtered page should be full, not a filtered slice of one page"
    assert all(r["room_category"] == "3br" for r in page)

    everything = client.get("/api/recommendations?room_category=3br&limit=2000").json()
    assert len(everything) > 10
    assert all(r["room_category"] == "3br" for r in everything)


def test_search_is_applied_before_paging(client):
    page = client.get("/api/recommendations?search=premium&limit=5").json()
    assert len(page) == 5
    assert all("premium" in r["room_category_label"].lower() for r in page)


def test_clearing_a_numeric_setting_does_not_blank_the_dashboard(client):
    """Regression: a null from the Settings UI skipped every row, committed an
    empty run, and returned 200 with a success message."""
    import copy

    config = client.get("/api/settings/config").json()
    before = len(client.get("/api/recommendations?limit=2000").json())

    payload = copy.deepcopy(config["payload"])
    payload["market"]["sensitivity"] = None      # exactly what a cleared field sends
    payload["dynamic"]["max_total_adjustment_pct"] = None
    response = client.put(
        "/api/settings/config", json={"payload": payload, "label": "nulled", "regenerate": True}
    )
    assert response.status_code == 200

    after = client.get("/api/recommendations?limit=2000").json()
    assert len(after) == before, "clearing a field must not destroy the pricing run"
    client.post("/api/settings/reset")


def test_updating_an_event_rejects_an_inverted_date_range(client):
    created = client.post(
        "/api/events",
        json={"name": "Editable", "start_date": "2026-11-01", "end_date": "2026-11-03"},
    ).json()
    response = client.put(
        f"/api/events/{created['id']}",
        json={"name": "Editable", "start_date": "2026-11-05", "end_date": "2026-11-01"},
    )
    assert response.status_code == 422, "an inverted range silently disables the event"
    client.delete(f"/api/events/{created['id']}")


def test_outcome_readiness_is_visible_to_the_operator(client):
    """Regression follow-up to #4: the outcome dataset existing in the database
    is not the same as the operator being able to see whether it is real.

    Outcomes attach to the historical run, which Rate Review never exposes, so
    the drawer's Outcome section is unreachable in demo mode by design. The
    status payload must therefore carry readiness for the banner to render.
    """
    readiness = client.get("/api/status").json()["outcome_readiness"]
    assert "real_outcomes" in readiness
    assert "synthetic_outcomes" in readiness
    assert readiness["synthetic_outcomes"] > 0, "demo outcomes should exist to be reported"
    assert readiness["note"], "readiness must explain what real capture requires"
    # Order-independent: readiness must track REAL outcomes only, never synthetic
    # ones. (An earlier test in this module records a real outcome, so the flag
    # may legitimately be True by the time this runs.)
    assert readiness["ready_for_evaluation"] is (readiness["real_outcomes"] > 0)


# --------------------------------------- codes must travel with their labels
def test_history_rows_carry_the_codes_their_labels_come_from(client):
    """A label can only be translated if the code that produced it is present.

    History served `room_category_label` and `season_label` as English strings
    with no accompanying code, so the frontend had nothing to look the
    Vietnamese wording up by -- the one screen that would have stayed English.
    """
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "i18n"})
    rows = client.get("/api/history").json()
    assert rows, "expected a decision to have been recorded"
    for row in rows:
        assert row["room_category"], "room_category code missing"
        assert row["season_key"], "season_key code missing"


def test_an_unpriced_row_still_says_why_it_could_not_be_priced(client):
    """The reason used to live in `explanation` and went with the column.

    An error-status row has no adjustments, so the drawer would render an empty
    breakdown and no reason at all — the operator would see a stay date sitting
    at its current rate with nothing saying the engine had failed on it.
    """
    from dynamic_pricing.models import PricingRecommendation

    rec = client.get("/api/recommendations?limit=1").json()[0]
    detail = client.get(f"/api/recommendations/{rec['id']}").json()
    assert "unpriced" in detail, "the payload must state whether this date was priced"
    assert detail["unpriced"] is False
    assert detail["unpriced_reason"] is None

    assert hasattr(PricingRecommendation, "extra")


def test_the_preview_endpoint_returns_structured_problems(client):
    """The preview is the surface that exists to report a bad field, so a schema
    that cannot carry the report 500s on exactly the input it was built for."""
    response = client.post(
        "/api/settings/preview", json={"payload": {"market": {"sensitivity": "banana"}}}
    )
    assert response.status_code == 200, response.text
    problems = response.json()["problems"]
    assert problems and problems[0]["code"] == "not_a_number"
    assert problems[0]["path"] == "market.sensitivity"


# ---------------------------------------------------------------------------
# Search must reach what the OPERATOR can read, not what the database stores.
#
# A tester typing "phòng ngủ" — the words printed on every row of the Vietnamese
# table — got no results, because search matched room_type_name and
# room_category_label, which are English. The frontend already owns the
# translations (D30), so it resolves what was typed into CODES and sends those;
# the backend never learns a second language.
# ---------------------------------------------------------------------------
def test_search_by_room_category_code_returns_only_that_category(client):
    rows = client.get("/api/recommendations?codes=2br_regular&limit=500").json()
    assert rows, "no rows came back for a category that exists in the demo data"
    assert {r["room_category"] for r in rows} == {"2br_regular"}


def test_search_by_season_key_returns_only_that_season(client):
    seasons = {r["season_key"] for r in client.get("/api/recommendations?limit=5000").json()}
    target = sorted(s for s in seasons if s)[0]
    rows = client.get(f"/api/recommendations?codes={target}&limit=500").json()
    assert rows
    assert {r["season_key"] for r in rows} == {target}


def test_several_codes_are_matched_as_alternatives(client):
    """"phòng ngủ" translates to EVERY room category, so codes must OR."""
    rows = client.get("/api/recommendations?codes=2br_regular,3br&limit=500").json()
    assert {r["room_category"] for r in rows} == {"2br_regular", "3br"}


def test_a_code_that_matches_nothing_returns_nothing(client):
    assert client.get("/api/recommendations?codes=no_such_code&limit=500").json() == []


def test_free_text_still_matches_real_world_names(client):
    """Property and room-type names are real data and are never translated.

    They stay free-text precisely because there is no code to resolve them to.
    """
    rows = client.get("/api/recommendations?search=Luminous&limit=500").json()
    assert rows, "the property name should still be searchable as free text"


def test_codes_and_free_text_are_alternatives_not_a_narrowing(client):
    """One search box, two mechanisms — a hit in EITHER must show the row.

    Anding them would mean a term that resolves to a code returns nothing,
    because that same term is not in the property name.
    """
    rows = client.get(
        "/api/recommendations?codes=2br_regular&search=Luminous&limit=500"
    ).json()
    categories = {r["room_category"] for r in rows}
    assert len(categories) > 1, (
        "codes and free text were ANDed; a row matching either one must be returned"
    )


def test_code_search_is_applied_before_paging(client):
    """The page must be a slice of the MATCHES, not a filter of one page.

    The free-text branch has its own version of this above; both mechanisms
    filter the full set, so both need it.
    """
    page = client.get("/api/recommendations?codes=3br&limit=5").json()
    assert len(page) == 5
    assert {r["room_category"] for r in page} == {"3br"}


# ---------------------------------------------------------------------------
# A booking row is ONE OCCUPIED UNIT-NIGHT, not a stay. This is the contract
# the calendar got wrong: it read `nights` as a stay length and drew bars
# spanning up to five days, smearing every unit-night across the calendar and
# rendering ~3.5x the occupancy that exists.
# ---------------------------------------------------------------------------
def test_a_booking_row_is_one_occupied_unit_night(client):
    """The row count for a night must equal that night's units_sold.

    This is the semantic the whole feature rests on, so it is asserted against
    the data rather than trusted. If a provider ever emits one row per STAY
    instead, this fails and the UI must be reconsidered before it silently
    starts under-counting.
    """
    recs = client.get("/api/recommendations?limit=5000").json()
    if not recs:
        pytest.skip("no recommendations to compare against")

    window = sorted({r["stay_date"] for r in recs})[:10]
    rows = client.get(
        f"/api/bookings?start_date={window[0]}&end_date={window[-1]}&limit=20000"
    ).json()

    counted: dict[tuple[int, str], int] = {}
    for b in rows:
        counted[(b["room_type_id"], b["stay_date"])] = (
            counted.get((b["room_type_id"], b["stay_date"]), 0) + 1
        )

    compared = 0
    for r in recs:
        if r["stay_date"] not in window or r["units_sold"] is None:
            continue
        got = counted.get((r["room_type_id"], r["stay_date"]), 0)
        assert got == r["units_sold"], (
            f"{r['stay_date']} room type {r['room_type_id']}: {got} booking rows "
            f"but units_sold={r['units_sold']} — a row is no longer one unit-night"
        )
        compared += 1
    assert compared, "the comparison never ran"


def test_the_api_publishes_nothing_a_span_could_be_built_from(client):
    """Neither an end date nor a length, so no caller can rebuild the fiction.

    A derived `last_night` was how it got drawn the first time: correct
    arithmetic over a field that does not mean what its name suggests. Removing
    the end date alone would have left `nights` sitting there for the next
    reader to make the same inference.
    """
    rows = client.get("/api/bookings?limit=50").json()
    assert rows
    for field in ("last_night", "nights"):
        assert field not in rows[0], (
            f"/api/bookings publishes `{field}` again — a row is one unit-night "
            "and cannot support a span"
        )


def test_every_returned_row_falls_inside_the_window(client):
    every = client.get("/api/bookings?limit=20000").json()
    dates = sorted({b["stay_date"] for b in every})
    lo, hi = dates[2], dates[5]
    rows = client.get(f"/api/bookings?start_date={lo}&end_date={hi}&limit=20000").json()
    assert rows
    assert all(lo <= b["stay_date"] <= hi for b in rows)


def test_cancelled_bookings_never_reach_the_calendar(client):
    rows = client.get("/api/bookings?limit=20000").json()
    assert all(r["status"] != "cancelled" for r in rows)


def test_unit_assignment_is_reported_as_absent_rather_than_invented(client):
    """physical_room_id is NULL on every seeded booking (ASSUMPTIONS U11)."""
    rows = client.get("/api/bookings?limit=200").json()
    assert all(r["physical_room_id"] is None for r in rows), (
        "bookings now carry unit assignments — the calendar can label real units"
    )


def test_observations_can_be_fetched_for_a_window(client):
    """A caller wanting a period had to fetch everything and hope.

    The default limit is 200; the demo already holds ~1,200 observations, so a
    market view that asked for "all of them" silently received the 200 most
    recent and drew its conclusions from a sixth of the data.
    """
    every = client.get("/api/market/observations?limit=5000").json()
    assert len(every) > 200, "this test is pointless unless the data exceeds one page"

    dates = sorted({o["stay_date"] for o in every})
    lo, hi = dates[1], dates[3]
    windowed = client.get(
        f"/api/market/observations?start_date={lo}&end_date={hi}&limit=5000"
    ).json()

    assert windowed, "a window inside the data returned nothing"
    assert all(lo <= o["stay_date"] <= hi for o in windowed)
    expected = sum(1 for o in every if lo <= o["stay_date"] <= hi)
    assert len(windowed) == expected, "the window dropped or duplicated rows"


def test_editing_a_rate_band_reprices_the_dates_it_covers(client):
    """A saved band that did not re-price left the calendar serving stale rates.

    Every recommendation anchors on a band and is clamped to it, so the two
    cannot be allowed to disagree — and nothing on screen said they did.
    """
    bands = client.get("/api/rate-book").json()
    band = next(b for b in bands if b["room_category"] and b["base_net_rate"])

    def rate_for(season_key: str, category: str):
        rows = client.get("/api/recommendations?limit=5000").json()
        hits = [
            r
            for r in rows
            if r["season_key"] == season_key and r["room_category"] == category
        ]
        return hits[0]["band_base_net_rate"] if hits else None

    before = rate_for(band["season_key"], band["room_category"])
    if before is None:
        pytest.skip("no recommendation covers this band's season in the demo window")

    moved = round(band["base_net_rate"] * 1.10)
    response = client.put(
        f"/api/rate-book/{band['id']}",
        json={
            "min_net_rate": band["min_net_rate"],
            "base_net_rate": moved,
            "max_net_rate": max(band["max_net_rate"], moved),
        },
    )
    assert response.status_code == 200

    after = rate_for(band["season_key"], band["room_category"])
    assert after == moved, (
        f"recommendations still anchor on {after}, not the saved {moved} — "
        "the edit did not re-price"
    )

    # Leave the demo data as it was found.
    client.post("/api/rate-book/reset")


# ------------------------------------------------------- PMS data source
# The developer/data panel: which PMS source is live, and the Blue Jay testing
# window. Persisted rather than env-only, because SNAPSHOT is meant to be the
# standing demo mode and a demo machine should not need a .env edit and a
# restart to get there.


def test_the_data_source_endpoint_names_the_active_source_and_the_alternatives(client):
    body = client.get("/api/pms/source").json()
    assert body["active"] in {"mock", "snapshot", "bluejay"}
    assert {"mock", "snapshot", "bluejay"} <= set(body["available"])


def test_each_offered_source_explains_what_it_is(client):
    """A switcher offering three opaque words is a trap for a non-technical
    operator: one of them silently stops using real data."""
    body = client.get("/api/pms/source").json()
    for entry in body["sources"]:
        assert entry["label_key"], entry


def test_switching_the_data_source_persists_it(client):
    assert client.put("/api/pms/source", json={"source": "snapshot"}).status_code == 200
    assert client.get("/api/pms/source").json()["active"] == "snapshot"
    client.put("/api/pms/source", json={"source": "mock"})
    assert client.get("/api/pms/source").json()["active"] == "mock"


def test_an_unknown_data_source_is_refused_and_names_the_valid_ones(client):
    response = client.put("/api/pms/source", json={"source": "postgres"})
    assert response.status_code == 422
    assert "mock" in response.text


def test_the_data_source_endpoint_reports_the_blue_jay_testing_window(client):
    window = client.get("/api/pms/source").json()["bluejay_window"]
    assert window["timezone"] == "Asia/Ho_Chi_Minh"
    assert isinstance(window["is_open"], bool)
    assert window["windows"], "the operator has to be told when calls are possible"


def test_the_unconfirmed_midnight_window_is_flagged_in_the_api(client):
    window = client.get("/api/pms/source").json()["bluejay_window"]
    assert any(w["confirmed"] is False for w in window["windows"])


def test_the_room_type_category_map_round_trips(client):
    payload = {"map": {"6153": "3br", "6154": "2br_premium"}}
    assert client.put("/api/pms/category-map", json=payload).status_code == 200
    assert client.get("/api/pms/category-map").json()["map"] == payload["map"]


def test_a_category_map_pointing_at_an_unknown_category_is_refused(client):
    """A typo here silently unmaps a whole room type."""
    response = client.put("/api/pms/category-map", json={"map": {"6153": "penthouse"}})
    assert response.status_code == 422
    assert "3br" in response.text


def test_the_category_map_survives_being_emptied(client):
    assert client.put("/api/pms/category-map", json={"map": {}}).status_code == 200
    assert client.get("/api/pms/category-map").json()["map"] == {}


def test_the_persisted_source_is_what_the_system_status_reports(client):
    """Otherwise the switcher is cosmetic: the panel would say SNAPSHOT while
    every sync kept pulling from whatever DATA_PROVIDER said at boot."""
    client.put("/api/pms/source", json={"source": "snapshot"})
    try:
        assert client.get("/api/status").json()["pms"]["mode"] == "snapshot"
    finally:
        client.put("/api/pms/source", json={"source": "mock"})
    assert client.get("/api/status").json()["pms"]["mode"] == "mock"


def test_switching_source_does_not_require_restarting_the_api(client):
    """A demo machine must be able to reach SNAPSHOT without a .env edit."""
    before = client.get("/api/status").json()["pms"]["mode"]
    client.put("/api/pms/source", json={"source": "snapshot"})
    after = client.get("/api/status").json()["pms"]["mode"]
    client.put("/api/pms/source", json={"source": before})
    assert (before, after) == ("mock", "snapshot")


def test_demo_mode_follows_the_active_source_not_the_environment(client):
    """A wrong "Demo data" chip is the label that stops an operator
    double-checking, so it must never be computed from a different input than
    the provider actually in use.

    The dangerous direction is DATA_PROVIDER=bluejay in .env with the operator
    switched to MOCK in the UI: demo_mode would read False and the chip would
    disappear while every number on screen is synthetic.
    """
    assert client.get("/api/status").json()["demo_mode"] is True
    client.put("/api/pms/source", json={"source": "snapshot"})
    try:
        body = client.get("/api/status").json()
        assert body["pms"]["mode"] == "snapshot"
        assert body["demo_mode"] is False, "demo_mode disagreed with the active provider"
    finally:
        client.put("/api/pms/source", json={"source": "mock"})
    assert client.get("/api/status").json()["demo_mode"] is True


def test_a_provider_can_raise_a_data_warning_separate_from_mapping_gaps(client):
    """Security warnings must not travel through `unresolved_mappings`.

    That field is named for room-type mapping gaps, so "this snapshot may
    contain guest data" rendered under a mapping heading reads as a
    configuration nit rather than as the warning it is.
    """
    body = client.get("/api/status").json()
    assert "warnings" in body["pms"], "ProviderStatus needs its own warning channel"
    assert isinstance(body["pms"]["warnings"], list)


def test_a_recommendation_says_where_its_current_rate_came_from(client):
    """Blue Jay publishes no forward rate, so in LIVE and SNAPSHOT most current
    rates are RECONSTRUCTED from bookings. An operator reading a realized
    average as a published list price is the one confusion this must prevent —
    and a value that is stored but never shown prevents nothing."""
    rows = client.get("/api/recommendations").json()
    assert rows, "no recommendations to check"
    assert "rate_provenance" in rows[0]
    assert rows[0]["rate_provenance"] == "published"


def test_the_last_syncs_data_findings_are_kept_where_a_human_can_read_them(client):
    """`POST /api/sync` returned them in a response body nothing consumed, so a
    warning that occupancy is overstated travelled one hop further than before
    and still stopped short of a person."""
    client.post("/api/sync?regenerate=false")
    status = client.get("/api/status").json()
    assert "last_sync_findings" in status
    assert isinstance(status["last_sync_findings"], dict)


def test_the_category_map_endpoint_offers_the_room_types_that_need_mapping(client):
    """The panel could only EDIT mappings that already existed.

    The ids needing attention come from `unmapped_room_type_ids`, which fed
    `unresolved_mappings` — a field rendered nowhere. So a new Blue Jay room
    type went unpriced, the provider correctly said so, and the panel that
    exists to fix it showed neither the id nor any warning.
    """
    body = client.get("/api/pms/category-map").json()
    assert "unmapped" in body
    assert isinstance(body["unmapped"], list)


def test_a_discovered_room_type_is_offered_with_its_name_not_just_its_id(client):
    """Choosing a pricing category for an opaque number is how the wrong id
    gets mapped, and a wrong mapping misprices an entire category silently."""
    for entry in client.get("/api/pms/category-map").json()["unmapped"]:
        assert "id" in entry and "name" in entry


def test_omitting_a_room_type_from_the_map_is_how_it_becomes_unmapped(client):
    """The panel offered a "Not mapped" option that sent "" — which the API
    rejects with a 422. There was no path that REMOVED a key, so the concept
    the option offered did not exist in the write path at all."""
    client.put("/api/pms/category-map", json={"map": {"6153": "3br", "6154": "2br_premium"}})
    assert client.put("/api/pms/category-map", json={"map": {"6153": "3br"}}).status_code == 200
    stored = client.get("/api/pms/category-map").json()["map"]
    assert stored == {"6153": "3br"}
    client.put("/api/pms/category-map", json={"map": {}})


def test_an_empty_category_is_refused_rather_than_stored_as_a_mapping(client):
    """`{"6153": ""}` was what the panel's own "Not mapped" option sent."""
    response = client.put("/api/pms/category-map", json={"map": {"6153": ""}})
    assert response.status_code == 422
