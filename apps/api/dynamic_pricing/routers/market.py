"""Market observations: manual entry, listing, and the public-web prototype."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import MarketObservation, Property, Room
from ..providers.market import get_market_provider
from ..providers.market.factory import list_market_providers
from ..providers.pms.base import ProviderUnavailable
from ..schemas import MarketCollectIn, MarketObservationIn, MarketObservationOut

router = APIRouter(prefix="/api/market", tags=["market"])


def _serialise(session: Session, obs: MarketObservation) -> dict:
    prop = session.get(Property, obs.property_id) if obs.property_id else None
    room = session.get(Room, obs.room_id) if obs.room_id else None
    return {
        "id": obs.id,
        "property_id": obs.property_id,
        "room_id": obs.room_id,
        "property_name": prop.name if prop else None,
        "room_name": room.name if room else None,
        "stay_date": obs.stay_date,
        "competitor_name": obs.competitor_name,
        "observed_price": obs.observed_price,
        "currency": obs.currency,
        "source": obs.source,
        "source_url": obs.source_url,
        "notes": obs.notes,
        "collected_at": obs.collected_at,
    }


@router.get("/observations", response_model=list[MarketObservationOut])
def list_observations(
    session: Session = Depends(get_session),
    room_id: int | None = None,
    property_id: int | None = None,
    stay_date: date | None = None,
    source: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
):
    query = select(MarketObservation).order_by(
        MarketObservation.collected_at.desc(), MarketObservation.id.desc()
    )
    if room_id:
        query = query.where(MarketObservation.room_id == room_id)
    if property_id:
        query = query.where(MarketObservation.property_id == property_id)
    if stay_date:
        query = query.where(MarketObservation.stay_date == stay_date)
    if source and source != "all":
        query = query.where(MarketObservation.source == source)
    return [_serialise(session, o) for o in session.scalars(query.limit(limit)).all()]


@router.post("/observations", response_model=MarketObservationOut, status_code=201)
def create_observation(body: MarketObservationIn, session: Session = Depends(get_session)):
    """Manual market entry — the always-available fallback signal."""
    property_id = body.property_id
    if body.room_id:
        room = session.get(Room, body.room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        property_id = room.property_id

    obs = MarketObservation(
        property_id=property_id,
        room_id=body.room_id,
        stay_date=body.stay_date,
        competitor_name=body.competitor_name,
        observed_price=body.observed_price,
        currency="VND",
        source=body.source or "manual",
        source_url=body.source_url,
        notes=body.notes,
        collected_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return _serialise(session, obs)


@router.delete("/observations/{observation_id}", status_code=204)
def delete_observation(observation_id: int, session: Session = Depends(get_session)):
    session.execute(delete(MarketObservation).where(MarketObservation.id == observation_id))
    session.commit()


@router.get("/providers")
def providers(session: Session = Depends(get_session)):
    out = []
    for key in list_market_providers():
        status = get_market_provider(key).status()
        out.append(
            {
                "key": key,
                "name": status.name,
                "healthy": status.healthy,
                "mode": status.mode,
                "detail": status.detail,
                "remediation": status.remediation,
            }
        )
    return out


@router.post("/collect")
def collect(body: MarketCollectIn, provider: str = "public_web", session: Session = Depends(get_session)):
    """Run the public-web prototype for one stay date.

    A failure here is reported, never fatal: the pricing engine simply falls
    back to a neutral market factor.
    """
    from ..services.sync import persist_observations

    room = session.get(Room, body.room_id) if body.room_id else None
    property_external_id = None
    if room:
        prop = session.get(Property, room.property_id)
        property_external_id = prop.external_id if prop else None

    market = get_market_provider(provider)
    try:
        observations = market.collect(
            body.stay_date,
            body.stay_date,
            stay_date=body.stay_date,
            room_external_id=room.external_id if room else None,
            property_external_id=property_external_id,
        )
    except ProviderUnavailable as exc:
        return {
            "ok": False,
            "collected": 0,
            "message": exc.message,
            "remediation": exc.remediation,
            "provider": market.name,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "collected": 0,
            "message": f"{type(exc).__name__}: {exc}",
            "remediation": "Use manual market entry instead.",
            "provider": market.name,
        }

    count = persist_observations(session, observations)
    session.commit()
    return {
        "ok": True,
        "collected": count,
        "message": f"Collected {count} observation(s).",
        "remediation": "",
        "provider": market.name,
    }
