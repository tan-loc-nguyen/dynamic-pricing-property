"""Normalization layer: provider DTOs -> domain rows.

The ONLY module that writes provider data into the database. Both the mock
provider and (once wired) Blue Jay travel this exact path, so demo mode
continuously proves the integration boundary works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Booking,
    Competitor,
    MarketObservation,
    PhysicalRoom,
    Property,
    RoomType,
    StayDateInventory,
)
from ..providers.market.base import MarketDataProvider, MarketObservationDTO, score_confidence
from ..providers.pms.base import PMSProvider, ProviderUnavailable


@dataclass
class SyncReport:
    provider: str
    properties: int = 0
    room_types: int = 0
    physical_rooms: int = 0
    inventory: int = 0
    bookings: int = 0
    market_observations: int = 0
    ok: bool = True
    message: str = ""
    remediation: str = ""

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "properties": self.properties,
            "room_types": self.room_types,
            "physical_rooms": self.physical_rooms,
            "inventory": self.inventory,
            "bookings": self.bookings,
            "market_observations": self.market_observations,
            "ok": self.ok,
            "message": self.message,
            "remediation": self.remediation,
        }


def sync_pms(
    session: Session,
    provider: PMSProvider,
    *,
    start: date,
    end: date,
    replace: bool = True,
) -> SyncReport:
    """Pull the portfolio from a PMS provider and persist it.

    A provider outage returns a failed report — it never raises into the
    caller, because an integration failure must not take the product down.
    """
    report = SyncReport(provider=provider.name)
    try:
        properties = provider.fetch_properties()
        room_types = provider.fetch_room_types()
        physical_rooms = provider.fetch_physical_rooms()
        inventory = provider.fetch_inventory(start, end)
        bookings = provider.fetch_bookings(start, end)
    except ProviderUnavailable as exc:
        report.ok = False
        report.message = exc.message
        report.remediation = exc.remediation
        return report
    except Exception as exc:  # noqa: BLE001 - any adapter bug degrades gracefully
        report.ok = False
        report.message = f"{type(exc).__name__}: {exc}"
        report.remediation = "Check provider configuration, or run with DATA_PROVIDER=mock."
        return report

    # --- properties ----------------------------------------------------
    prop_by_ext = {p.external_id: p for p in session.scalars(select(Property)).all()}
    for dto in properties:
        row = prop_by_ext.get(dto.external_id)
        if row is None:
            row = Property(external_id=dto.external_id)
            session.add(row)
            prop_by_ext[dto.external_id] = row
        row.name = dto.name
        row.city = dto.city
        row.district = dto.district
        row.currency = dto.currency
        row.timezone_name = dto.timezone_name
        row.source = provider.mode
        report.properties += 1
    session.flush()

    # --- room types -----------------------------------------------------
    rt_by_ext = {r.external_id: r for r in session.scalars(select(RoomType)).all()}
    for dto in room_types:
        parent = prop_by_ext.get(dto.property_external_id)
        if parent is None:
            continue
        row = rt_by_ext.get(dto.external_id)
        if row is None:
            row = RoomType(external_id=dto.external_id, property_id=parent.id)
            session.add(row)
            rt_by_ext[dto.external_id] = row
        row.property_id = parent.id
        row.name = dto.name
        row.category = dto.category
        row.capacity = dto.capacity
        row.units_total = dto.units_total
        row.fallback_base_net_rate = dto.fallback_base_net_rate
        row.fallback_min_net_rate = dto.fallback_min_net_rate
        row.fallback_max_net_rate = dto.fallback_max_net_rate
        row.is_active = dto.is_active
        row.source = provider.mode
        report.room_types += 1
    session.flush()

    # --- physical rooms ---------------------------------------------------
    pr_by_ext = {r.external_id: r for r in session.scalars(select(PhysicalRoom)).all()}
    for dto in physical_rooms:
        parent = rt_by_ext.get(dto.room_type_external_id)
        if parent is None:
            continue
        row = pr_by_ext.get(dto.external_id)
        if row is None:
            row = PhysicalRoom(external_id=dto.external_id, room_type_id=parent.id)
            session.add(row)
            pr_by_ext[dto.external_id] = row
        row.room_type_id = parent.id
        row.unit_label = dto.unit_label
        row.floor = dto.floor
        row.is_active = dto.is_active
        row.source = provider.mode
        report.physical_rooms += 1
    session.flush()

    # --- inventory + bookings ---------------------------------------------
    if replace:
        session.execute(
            delete(StayDateInventory).where(
                StayDateInventory.stay_date >= start, StayDateInventory.stay_date <= end
            )
        )
        session.execute(delete(Booking).where(Booking.stay_date >= start, Booking.stay_date <= end))
        session.flush()

    for dto in inventory:
        rt = rt_by_ext.get(dto.room_type_external_id)
        if rt is None:
            continue
        session.add(
            StayDateInventory(
                room_type_id=rt.id,
                stay_date=dto.stay_date,
                units_total=dto.units_total,
                units_sold=dto.units_sold,
                current_net_rate=dto.current_net_rate,
                current_ota_price=dto.current_ota_price,
                historical_occupancy=dto.historical_occupancy,
                historical_avg_net_rate=dto.historical_avg_net_rate,
                source=provider.mode,
            )
        )
        report.inventory += 1

    for dto in bookings:
        rt = rt_by_ext.get(dto.room_type_external_id)
        if rt is None:
            continue
        session.add(
            Booking(
                external_id=dto.external_id,
                room_type_id=rt.id,
                stay_date=dto.stay_date,
                booked_at=dto.booked_at,
                nights=dto.nights,
                guests=dto.guests,
                net_rate=dto.net_rate,
                channel=dto.channel,
                status=dto.status,
                source=provider.mode,
            )
        )
        report.bookings += 1

    session.commit()
    report.message = "Portfolio synchronised."
    return report


def sync_market(
    session: Session,
    provider: MarketDataProvider,
    *,
    start: date,
    end: date,
    replace_source: bool = True,
    **kwargs,
) -> SyncReport:
    """Pull market observations. Never raises; a failure degrades to neutral."""
    report = SyncReport(provider=provider.name)
    try:
        observations = provider.collect(start, end, **kwargs)
    except ProviderUnavailable as exc:
        report.ok = False
        report.message = exc.message
        report.remediation = exc.remediation
        return report
    except Exception as exc:  # noqa: BLE001
        report.ok = False
        report.message = f"{type(exc).__name__}: {exc}"
        report.remediation = "Falling back to a neutral market adjustment."
        return report

    if replace_source and observations:
        sources = {o.source for o in observations}
        session.execute(
            delete(MarketObservation).where(
                MarketObservation.source.in_(sources),
                MarketObservation.stay_date >= start,
                MarketObservation.stay_date <= end,
            )
        )
        session.flush()

    report.market_observations = persist_observations(session, observations)
    session.commit()
    report.message = f"Collected {report.market_observations} market observation(s)."
    return report


def persist_observations(session: Session, observations: list[MarketObservationDTO]) -> int:
    """Map observation DTOs onto domain rows, resolving ids and scoring confidence."""
    if not observations:
        return 0

    prop_by_ext = {p.external_id: p for p in session.scalars(select(Property)).all()}
    rt_by_ext = {r.external_id: r for r in session.scalars(select(RoomType)).all()}
    comp_by_name = {c.name: c for c in session.scalars(select(Competitor)).all()}

    count = 0
    for dto in observations:
        rt = rt_by_ext.get(dto.room_type_external_id) if dto.room_type_external_id else None
        prop = prop_by_ext.get(dto.property_external_id) if dto.property_external_id else None
        if prop is None and rt is not None:
            prop = session.get(Property, rt.property_id)

        # Auto-register unseen comp-set members so the comp set stays curatable.
        competitor = comp_by_name.get(dto.competitor_name)
        if competitor is None:
            competitor = Competitor(
                property_id=prop.id if prop else None,
                name=dto.competitor_name,
                comparable_category=dto.room_category,
                source=dto.source,
                source_url=dto.source_url,
            )
            session.add(competitor)
            session.flush()
            comp_by_name[dto.competitor_name] = competitor

        confidence = dto.confidence
        reason = dto.confidence_reason
        reason_code, gaps = None, []
        if not confidence:
            confidence, reason_code, gaps = score_confidence(dto)
            reason = None

        session.add(
            MarketObservation(
                property_id=prop.id if prop else None,
                room_type_id=rt.id if rt else None,
                competitor_id=competitor.id,
                stay_date=dto.stay_date,
                competitor_name=dto.competitor_name,
                observed_price=dto.observed_price,
                currency=dto.currency,
                room_category=dto.room_category,
                length_of_stay=dto.length_of_stay,
                guests=dto.guests,
                price_basis=dto.price_basis,
                tax_inclusion=dto.tax_inclusion,
                fee_inclusion=dto.fee_inclusion,
                promotion_status=dto.promotion_status,
                is_refundable=dto.is_refundable,
                confidence=confidence,
                confidence_reason=reason,
                confidence_code=reason_code,
                confidence_gaps=gaps,
                source=dto.source,
                source_url=dto.source_url,
                notes=dto.notes,
                observed_at=dto.observed_at,
            )
        )
        count += 1
    return count


def default_window(today: date, history_days: int = 45, horizon_days: int = 90) -> tuple[date, date]:
    return today - timedelta(days=history_days), today + timedelta(days=horizon_days)
