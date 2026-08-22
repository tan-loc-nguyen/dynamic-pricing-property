"""Normalization layer: provider DTOs -> domain rows.

This is the ONLY module that writes provider data into the database. Both the
mock provider and (once wired) Blue Jay travel this exact path, so demo mode
continuously proves the integration boundary works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Booking, MarketObservation, Property, Room, StayDateInventory
from ..providers.market.base import MarketDataProvider, MarketObservationDTO
from ..providers.pms.base import PMSProvider, ProviderUnavailable


@dataclass
class SyncReport:
    provider: str
    properties: int = 0
    rooms: int = 0
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
            "rooms": self.rooms,
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

    A provider outage returns a failed report — it never raises into the caller,
    because an integration failure must not take the product down.
    """
    report = SyncReport(provider=provider.name)
    try:
        properties = provider.fetch_properties()
        rooms = provider.fetch_rooms()
        inventory = provider.fetch_inventory(start, end)
        bookings = provider.fetch_bookings(start, end)
    except ProviderUnavailable as exc:
        report.ok = False
        report.message = exc.message
        report.remediation = exc.remediation
        return report
    except Exception as exc:  # noqa: BLE001 - defensive: any adapter bug degrades gracefully
        report.ok = False
        report.message = f"{type(exc).__name__}: {exc}"
        report.remediation = "Check provider configuration, or run with DATA_PROVIDER=mock."
        return report

    # --- properties ----------------------------------------------------
    prop_by_ext: dict[str, Property] = {
        p.external_id: p for p in session.scalars(select(Property)).all()
    }
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

    # --- rooms ---------------------------------------------------------
    room_by_ext: dict[str, Room] = {r.external_id: r for r in session.scalars(select(Room)).all()}
    for dto in rooms:
        parent = prop_by_ext.get(dto.property_external_id)
        if parent is None:
            continue
        row = room_by_ext.get(dto.external_id)
        if row is None:
            row = Room(external_id=dto.external_id, property_id=parent.id)
            session.add(row)
            room_by_ext[dto.external_id] = row
        row.property_id = parent.id
        row.name = dto.name
        row.room_type = dto.room_type
        row.capacity = dto.capacity
        row.units_total = dto.units_total
        row.base_price = dto.base_price
        if dto.min_price is not None:
            row.min_price = dto.min_price
        if dto.max_price is not None:
            row.max_price = dto.max_price
        row.is_active = dto.is_active
        row.source = provider.mode
        report.rooms += 1
    session.flush()

    # --- inventory + bookings -------------------------------------------
    if replace:
        session.execute(
            delete(StayDateInventory).where(
                StayDateInventory.stay_date >= start, StayDateInventory.stay_date <= end
            )
        )
        session.execute(
            delete(Booking).where(Booking.stay_date >= start, Booking.stay_date <= end)
        )
        session.flush()

    for dto in inventory:
        room = room_by_ext.get(dto.room_external_id)
        if room is None:
            continue
        session.add(
            StayDateInventory(
                room_id=room.id,
                stay_date=dto.stay_date,
                units_total=dto.units_total,
                units_sold=dto.units_sold,
                current_price=dto.current_price,
                is_event=dto.is_event,
                event_name=dto.event_name,
                season=dto.season,
                historical_occupancy=dto.historical_occupancy,
                historical_avg_price=dto.historical_avg_price,
                source=provider.mode,
            )
        )
        report.inventory += 1

    for dto in bookings:
        room = room_by_ext.get(dto.room_external_id)
        if room is None:
            continue
        session.add(
            Booking(
                external_id=dto.external_id,
                room_id=room.id,
                stay_date=dto.stay_date,
                booked_at=dto.booked_at,
                nights=dto.nights,
                guests=dto.guests,
                price=dto.price,
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
        report.remediation = "Falling back to a neutral market factor."
        return report

    if replace_source and observations:
        source = observations[0].source
        session.execute(
            delete(MarketObservation).where(
                MarketObservation.source == source,
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
    """Map observation DTOs onto domain rows, resolving external ids."""
    if not observations:
        return 0
    prop_by_ext = {p.external_id: p for p in session.scalars(select(Property)).all()}
    room_by_ext = {r.external_id: r for r in session.scalars(select(Room)).all()}

    count = 0
    for dto in observations:
        room = room_by_ext.get(dto.room_external_id) if dto.room_external_id else None
        prop = prop_by_ext.get(dto.property_external_id) if dto.property_external_id else None
        if prop is None and room is not None:
            prop = session.get(Property, room.property_id)
        session.add(
            MarketObservation(
                property_id=prop.id if prop else None,
                room_id=room.id if room else None,
                stay_date=dto.stay_date,
                competitor_name=dto.competitor_name,
                observed_price=dto.observed_price,
                currency=dto.currency,
                source=dto.source,
                source_url=dto.source_url,
                notes=dto.notes,
                collected_at=dto.collected_at,
            )
        )
        count += 1
    return count


def default_window(today: date, history_days: int = 45, horizon_days: int = 60) -> tuple[date, date]:
    return today - timedelta(days=history_days), today + timedelta(days=horizon_days)
