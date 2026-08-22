"""End-to-end workflow: seed -> recommend -> accept/override -> history.

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


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_data_is_seeded_on_startup(client):
    counts = client.get("/api/status").json()["counts"]
    assert counts["properties"] >= 3
    assert counts["rooms"] >= 8
    assert counts["recommendations"] > 100
    assert counts["market_observations"] > 0


def test_status_reports_provider_health_honestly(client):
    status = client.get("/api/status").json()
    assert status["pms"]["healthy"] is True
    assert status["demo_mode"] is True
    assert status["engine"]["version"] == "v1.0.0"
    assert len(status["override_reasons"]) == 8


def test_recommendations_are_varied(client):
    recs = client.get("/api/recommendations?limit=500").json()
    assert len(recs) > 100
    prices = {r["recommended_price"] for r in recs}
    assert len(prices) > 20, "engine should not return a flat price for every date"
    changes = [r["change_pct"] for r in recs]
    assert max(changes) > 0 and min(changes) < 0


def test_demo_covers_every_teaching_scenario(client):
    recs = client.get("/api/recommendations?limit=1000").json()
    assert any(r["is_event"] for r in recs), "no event date"
    assert any(r["market_price_index"] is None for r in recs), "no missing-market date"
    assert any((r["occupancy"] or 0) >= 0.85 for r in recs), "no high-occupancy date"
    assert any((r["occupancy"] or 1) <= 0.20 for r in recs), "no low-occupancy date"
    assert any(r["day_of_week"] == "saturday" for r in recs)

    detailed = [client.get(f"/api/recommendations/{r['id']}").json() for r in recs[:80]]
    all_recs = detailed + [
        client.get(f"/api/recommendations/{r['id']}").json()
        for r in recs
        if r["room_name"] in ("Thao Dien Duplex Loft", "Riverside Two-Bedroom Suite")
    ][:60]
    bounds = {d["metadata"].get("bounds_applied") for d in all_recs}
    assert "min" in bounds or "max" in bounds, "no price-bound scenario in the demo"


def test_every_recommendation_is_explainable(client):
    recs = client.get("/api/recommendations?limit=25").json()
    for rec in recs:
        detail = client.get(f"/api/recommendations/{rec['id']}").json()
        assert detail["adjustments"], "recommendation with no breakdown"
        assert detail["explanation"]
        assert detail["engine_version"]
        # the breakdown must reconcile to the final price
        running = detail["base_price"]
        for adj in detail["adjustments"]:
            assert adj["price_before"] == pytest.approx(running, abs=0.02)
            running = adj["price_after"]
        assert detail["recommended_price"] == pytest.approx(running, abs=0.02)


def test_accept_persists_a_decision_and_applies_the_price(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    result = client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "ok"}).json()

    assert result["status"] == "accepted"
    decision = result["decisions"][0]
    assert decision["final_price"] == rec["recommended_price"]
    assert decision["previous_price"] == rec["current_price"]
    assert decision["engine_version"] and decision["config_version"]

    # the approved price becomes the current price
    refreshed = client.get(f"/api/recommendations/{rec['id']}").json()
    assert refreshed["status"] == "accepted"


def test_override_persists_price_reason_and_note(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    result = client.post(
        f"/api/recommendations/{rec['id']}/override",
        json={"final_price": 1_111_000, "reason_code": "owner_constraint", "note": "owner floor"},
    ).json()

    assert result["status"] == "overridden"
    decision = result["decisions"][0]
    assert decision["final_price"] == 1_111_000
    assert decision["reason_code"] == "owner_constraint"
    assert decision["reason_label"] == "Owner constraint"
    assert decision["note"] == "owner floor"


def test_override_rejects_an_unknown_reason(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    response = client.post(
        f"/api/recommendations/{rec['id']}/override",
        json={"final_price": 1_000_000, "reason_code": "made_up_reason"},
    )
    assert response.status_code == 422


def test_history_shows_both_decisions(client):
    history = client.get("/api/history").json()
    assert len(history) >= 2
    kinds = {h["decision"] for h in history}
    assert {"accepted", "overridden"} <= kinds
    override = next(h for h in history if h["decision"] == "overridden")
    assert override["reason_label"]
    assert override["difference"] != 0


def test_summary_reflects_the_decisions(client):
    summary = client.get("/api/recommendations/summary").json()
    assert summary["accepted_recommendations"] >= 1
    assert summary["overridden_recommendations"] >= 1
    assert summary["active_rooms"] >= 8


# ------------------------------------------------------------------ settings
def test_changing_settings_changes_recommendations(client):
    config = client.get("/api/settings/config").json()
    before = client.get("/api/recommendations?limit=200").json()
    saturdays_before = [r for r in before if r["day_of_week"] == "saturday"]
    assert saturdays_before

    payload = config["payload"]
    payload["day_of_week"]["multipliers"]["saturday"] = 1.45
    saved = client.put(
        "/api/settings/config", json={"payload": payload, "label": "test", "regenerate": True}
    ).json()
    assert saved["version"] > config["version"]

    after = client.get("/api/recommendations?limit=200").json()
    saturdays_after = [r for r in after if r["day_of_week"] == "saturday"]
    key = lambda rows: {(r["room_id"], r["stay_date"]): r["recommended_price"] for r in rows}
    before_map, after_map = key(saturdays_before), key(saturdays_after)
    shared = set(before_map) & set(after_map)
    assert shared
    assert any(after_map[k] > before_map[k] for k in shared), "Saturday uplift had no effect"


def test_reset_restores_demo_defaults(client):
    reset = client.post("/api/settings/reset").json()
    assert reset["label"] == "demo-defaults"
    assert reset["payload"]["day_of_week"]["multipliers"]["saturday"] == 1.15


def test_preview_prices_an_unsaved_configuration(client):
    config = client.get("/api/settings/config").json()["payload"]
    baseline = client.post("/api/settings/preview", json={"payload": config}).json()

    import copy

    edited = copy.deepcopy(config)
    edited["pricing"]["base_price_override"] = 5_000_000
    preview = client.post("/api/settings/preview", json={"payload": edited}).json()

    assert preview["recommended_price"] > baseline["recommended_price"]
    # preview must NOT persist
    assert client.get("/api/settings/config").json()["payload"]["pricing"]["base_price_override"] is None


# -------------------------------------------------------------------- market
def test_manual_market_observation_flows_into_the_signal(client):
    recs = client.get("/api/recommendations?limit=500").json()
    target = next(r for r in recs if r["market_price_index"] is None)

    for i in range(3):
        response = client.post(
            "/api/market/observations",
            json={
                "stay_date": target["stay_date"],
                "competitor_name": f"Manual Comp {i}",
                "observed_price": 9_000_000,
                "room_id": target["room_id"],
                "source": "manual",
                "notes": "entered by hand",
            },
        )
        assert response.status_code == 201

    client.post("/api/recommendations/generate")
    refreshed = next(
        r
        for r in client.get("/api/recommendations?limit=500").json()
        if r["room_id"] == target["room_id"] and r["stay_date"] == target["stay_date"]
    )
    assert refreshed["market_observation_count"] >= 3
    assert refreshed["market_price_index"] is not None


def test_market_providers_report_status(client):
    providers = {p["key"]: p for p in client.get("/api/market/providers").json()}
    assert providers["mock"]["healthy"] is True
    assert providers["manual"]["healthy"] is True
    # public collection is disabled by default and must say so rather than fail
    assert providers["public_web"]["healthy"] is False
    assert providers["public_web"]["remediation"]


def test_public_collector_fails_gracefully(client):
    result = client.post("/api/market/collect", json={"stay_date": "2026-09-20"}).json()
    assert result["ok"] is False
    assert result["collected"] == 0
    assert result["remediation"], "a failure must tell the operator what to do instead"


def test_engines_are_listed_for_pluggability(client):
    engines = client.get("/api/engines").json()
    assert any(e["key"] == "v1" for e in engines)


# ------------------------------------------------- regression: audit integrity
def test_recalculating_does_not_duplicate_decision_history(client):
    """A decision is a historical fact — recalculating must not clone it.

    Regression: carry-forward used to copy OperatorDecision rows onto each new
    recommendation, so History grew a duplicate row on every recalculation.
    """
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    client.post(f"/api/recommendations/{rec['id']}/accept", json={"note": "audit test"})

    before = len(client.get("/api/history?limit=1000").json())
    for _ in range(3):
        client.post("/api/recommendations/generate")
    after = len(client.get("/api/history?limit=1000").json())

    assert after == before, f"history grew from {before} to {after} across recalculations"


def test_decision_history_survives_recalculation_on_the_detail_view(client):
    rec = client.get("/api/recommendations?status=pending&limit=1").json()[0]
    client.post(
        f"/api/recommendations/{rec['id']}/override",
        json={"final_price": 1_777_000, "reason_code": "promotion", "note": "flash sale"},
    )
    client.post("/api/recommendations/generate")

    current = next(
        r
        for r in client.get("/api/recommendations?limit=1000").json()
        if r["room_id"] == rec["room_id"] and r["stay_date"] == rec["stay_date"]
    )
    detail = client.get(f"/api/recommendations/{current['id']}").json()
    notes = [d["note"] for d in detail["decisions"]]
    assert "flash sale" in notes, "past decisions must still be visible after recalculation"
    assert len(detail["decisions"]) == len({d["id"] for d in detail["decisions"]}), "duplicate decisions"
