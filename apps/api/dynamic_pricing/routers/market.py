"""Market observations, comp set, and the public-web prototype."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..constants import CONFIDENCE_LEVELS, INCLUSION_OPTIONS, PRICE_BASES, PROMOTION_OPTIONS
from ..db import get_session
from ..models import Competitor, MarketObservation, Property, RoomType
from ..providers.market import get_market_provider, score_confidence
from ..providers.market.base import MarketObservationDTO
from ..providers.market.factory import list_market_providers
from ..providers.pms.base import ProviderUnavailable
from ..schemas import (
    CompetitorIn,
    CompetitorOut,
    MarketCollectIn,
    MarketObservationIn,
    MarketObservationOut,
)

router = APIRouter(prefix="/api/market", tags=["market"])


def _serialise(session: Session, obs: MarketObservation) -> dict:
    rt = session.get(RoomType, obs.room_type_id) if obs.room_type_id else None
    return {
        "id": obs.id,
        "property_id": obs.property_id,
        "room_type_id": obs.room_type_id,
        "competitor_id": obs.competitor_id,
        "room_type_name": rt.name if rt else None,
        "stay_date": obs.stay_date,
        "competitor_name": obs.competitor_name,
        "observed_price": obs.observed_price,
        "currency": obs.currency,
        "room_category": obs.room_category,
        "length_of_stay": obs.length_of_stay,
        "guests": obs.guests,
        "price_basis": obs.price_basis,
        "tax_inclusion": obs.tax_inclusion,
        "fee_inclusion": obs.fee_inclusion,
        "promotion_status": obs.promotion_status,
        "is_refundable": obs.is_refundable,
        "confidence": obs.confidence,
        "confidence_reason": obs.confidence_reason,
        "source": obs.source,
        "source_url": obs.source_url,
        "notes": obs.notes,
        "observed_at": obs.observed_at,
    }


# ----------------------------------------------------------------- comp set
@router.get("/competitors", response_model=list[CompetitorOut])
def list_competitors(session: Session = Depends(get_session), include_inactive: bool = True):
    query = select(Competitor).order_by(Competitor.name)
    if not include_inactive:
        query = query.where(Competitor.is_active.is_(True))
    out = []
    for c in session.scalars(query).all():
        count = int(
            session.scalar(
                select(func.count())
                .select_from(MarketObservation)
                .where(MarketObservation.competitor_id == c.id)
            )
            or 0
        )
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "comparable_category": c.comparable_category,
                "source": c.source,
                "source_url": c.source_url,
                "is_active": c.is_active,
                "notes": c.notes,
                "observation_count": count,
            }
        )
    return out


@router.post("/competitors", response_model=CompetitorOut, status_code=201)
def create_competitor(body: CompetitorIn, session: Session = Depends(get_session)):
    prop = session.scalars(select(Property)).first()
    competitor = Competitor(property_id=prop.id if prop else None, **body.model_dump())
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return {**body.model_dump(), "id": competitor.id, "observation_count": 0}


@router.put("/competitors/{competitor_id}", response_model=CompetitorOut)
def update_competitor(competitor_id: int, body: CompetitorIn, session: Session = Depends(get_session)):
    competitor = session.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    for key, value in body.model_dump().items():
        setattr(competitor, key, value)
    session.commit()
    session.refresh(competitor)
    count = int(
        session.scalar(
            select(func.count())
            .select_from(MarketObservation)
            .where(MarketObservation.competitor_id == competitor.id)
        )
        or 0
    )
    return {**body.model_dump(), "id": competitor.id, "observation_count": count}


@router.delete("/competitors/{competitor_id}", status_code=204)
def delete_competitor(competitor_id: int, session: Session = Depends(get_session)):
    session.execute(delete(Competitor).where(Competitor.id == competitor_id))
    session.commit()


# ------------------------------------------------------------- observations
@router.get("/observations", response_model=list[MarketObservationOut])
def list_observations(
    session: Session = Depends(get_session),
    room_type_id: int | None = None,
    stay_date: date | None = None,
    source: str | None = None,
    confidence: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
):
    query = select(MarketObservation).order_by(
        MarketObservation.observed_at.desc(), MarketObservation.id.desc()
    )
    if room_type_id:
        query = query.where(MarketObservation.room_type_id == room_type_id)
    if stay_date:
        query = query.where(MarketObservation.stay_date == stay_date)
    if source and source != "all":
        query = query.where(MarketObservation.source == source)
    if confidence and confidence != "all":
        query = query.where(MarketObservation.confidence == confidence)
    return [_serialise(session, o) for o in session.scalars(query.limit(limit)).all()]


@router.get("/meta")
def market_meta():
    """Vocabulary for the observation form, served from the backend."""
    return {
        "confidence_levels": CONFIDENCE_LEVELS,
        "price_bases": PRICE_BASES,
        "inclusion_options": INCLUSION_OPTIONS,
        "promotion_options": PROMOTION_OPTIONS,
    }


@router.post("/observations", response_model=MarketObservationOut, status_code=201)
def create_observation(body: MarketObservationIn, session: Session = Depends(get_session)):
    """Manual market entry — the only path that can reach HIGH confidence."""
    property_id = body.property_id
    room_category = body.room_category
    if body.room_type_id:
        rt = session.get(RoomType, body.room_type_id)
        if rt is None:
            raise HTTPException(status_code=404, detail="Room type not found")
        property_id = rt.property_id
        room_category = room_category or rt.category

    dto = MarketObservationDTO(
        stay_date=body.stay_date,
        competitor_name=body.competitor_name,
        observed_price=body.observed_price,
        source=body.source or "manual",
        room_category=room_category,
        length_of_stay=body.length_of_stay,
        guests=body.guests,
        price_basis=body.price_basis,
        tax_inclusion=body.tax_inclusion,
        fee_inclusion=body.fee_inclusion,
        promotion_status=body.promotion_status,
        is_refundable=body.is_refundable,
        source_url=body.source_url,
        notes=body.notes,
    )
    confidence, reason = score_confidence(dto)

    competitor = session.scalars(
        select(Competitor).where(Competitor.name == body.competitor_name)
    ).first()
    if competitor is None:
        competitor = Competitor(
            property_id=property_id,
            name=body.competitor_name,
            comparable_category=room_category,
            source=body.source or "manual",
            source_url=body.source_url,
        )
        session.add(competitor)
        session.flush()

    obs = MarketObservation(
        property_id=property_id,
        room_type_id=body.room_type_id,
        competitor_id=competitor.id,
        stay_date=body.stay_date,
        competitor_name=body.competitor_name,
        observed_price=body.observed_price,
        currency="VND",
        room_category=room_category,
        length_of_stay=body.length_of_stay,
        guests=body.guests,
        price_basis=body.price_basis,
        tax_inclusion=body.tax_inclusion,
        fee_inclusion=body.fee_inclusion,
        promotion_status=body.promotion_status,
        is_refundable=body.is_refundable,
        confidence=confidence,
        confidence_reason=reason,
        source=body.source or "manual",
        source_url=body.source_url,
        notes=body.notes,
        observed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return _serialise(session, obs)


@router.delete("/observations/{observation_id}", status_code=204)
def delete_observation(observation_id: int, session: Session = Depends(get_session)):
    session.execute(delete(MarketObservation).where(MarketObservation.id == observation_id))
    session.commit()


# ------------------------------------------------------------------ providers
@router.get("/providers")
def providers():
    out = []
    for key in list_market_providers():
        provider = get_market_provider(key)
        status = provider.status()
        out.append(
            {
                "key": key,
                "name": status.name,
                "healthy": status.healthy,
                "mode": status.mode,
                "detail": status.detail,
                "remediation": status.remediation,
                "max_confidence": provider.max_confidence,
            }
        )
    return out


@router.post("/collect")
def collect(
    body: MarketCollectIn,
    provider: str = "public_web",
    session: Session = Depends(get_session),
):
    """Run the public-web prototype for one stay date.

    Anything it returns is LOW confidence by construction, so it will be shown
    to the operator but will not move a recommended rate.
    """
    from ..services.sync import persist_observations

    rt = session.get(RoomType, body.room_type_id) if body.room_type_id else None
    property_external_id = None
    if rt:
        prop = session.get(Property, rt.property_id)
        property_external_id = prop.external_id if prop else None

    market = get_market_provider(provider)
    try:
        observations = market.collect(
            body.stay_date,
            body.stay_date,
            stay_date=body.stay_date,
            room_type_external_id=rt.external_id if rt else None,
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
        "message": (
            f"Collected {count} observation(s) at LOW confidence — shown to you, but not "
            f"used to move rates."
        ),
        "remediation": "",
        "provider": market.name,
    }
