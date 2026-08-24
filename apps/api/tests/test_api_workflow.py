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


# ------------------------------------------------------------------- system
def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_data_is_seeded_on_startup(client):
    counts = client.get("/api/status").json()["counts"]
    assert counts["room_types"] == 3
    assert counts["physical_rooms"] == 22, "the client operates 22 apartments"
    assert counts["rate_bands"] == 15
    assert counts["recommendations"] > 100
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


def test_both_engines_are_registered(client):
    keys = {e["key"] for e in client.get("/api/engines").json()}
    assert {"v1", "v2"} <= keys


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
        assert detail["explanation"]
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
    assert "not reliably comparable" in body["confidence_reason"].lower()


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
