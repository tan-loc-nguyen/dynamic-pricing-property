"""SQLAlchemy domain model.

Deliberately small. A "Room" models a *room type* that has N physical units,
because occupancy only becomes a meaningful pricing signal when there is more
than one sellable unit. See docs/DECISIONS.md (D2).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(80), default="Ho Chi Minh City")
    district: Mapped[str] = mapped_column(String(80), default="")
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    timezone_name: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    source: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    rooms: Mapped[list["Room"]] = relationship(back_populates="property", cascade="all, delete-orphan")


class Room(Base):
    """A sellable room type within a property (may have several units)."""

    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("property_id", "external_id", name="uq_room_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    room_type: Mapped[str] = mapped_column(String(80), default="Studio")
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    units_total: Mapped[int] = mapped_column(Integer, default=4)

    # Provisional commercial guardrails (UNVALIDATED — see ASSUMPTIONS.md A1/A2/A3)
    base_price: Mapped[float] = mapped_column(Float, default=1_500_000.0)
    min_price: Mapped[float] = mapped_column(Float, default=900_000.0)
    max_price: Mapped[float] = mapped_column(Float, default=3_500_000.0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    property: Mapped[Property] = relationship(back_populates="rooms")
    inventory: Mapped[list["StayDateInventory"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class StayDateInventory(Base):
    """One room type on one stay date: the atomic unit that gets priced."""

    __tablename__ = "stay_date_inventory"
    __table_args__ = (UniqueConstraint("room_id", "stay_date", name="uq_inventory_room_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    units_total: Mapped[int] = mapped_column(Integer, default=4)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)
    current_price: Mapped[float] = mapped_column(Float, default=1_500_000.0)

    is_event: Mapped[bool] = mapped_column(Boolean, default=False)
    event_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    season: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Same-room historical reference for the same weekday (demo-generated).
    historical_occupancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(32), default="mock")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    room: Mapped[Room] = relationship(back_populates="inventory")

    @property
    def occupancy(self) -> float | None:
        if not self.units_total:
            return None
        return round(self.units_sold / self.units_total, 4)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)
    booked_at: Mapped[date] = mapped_column(Date, index=True)
    nights: Mapped[int] = mapped_column(Integer, default=1)
    guests: Mapped[int] = mapped_column(Integer, default=2)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    channel: Mapped[str] = mapped_column(String(48), default="Airbnb")
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    source: Mapped[str] = mapped_column(String(32), default="mock")

    @property
    def lead_time_days(self) -> int:
        return max((self.stay_date - self.booked_at).days, 0)


class MarketObservation(Base):
    """A single observed competitor/reference price for a stay date."""

    __tablename__ = "market_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    competitor_name: Mapped[str] = mapped_column(String(160))
    observed_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    source: Mapped[str] = mapped_column(String(48), default="mock")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PricingConfiguration(Base):
    """Versioned snapshot of every provisional business assumption.

    Stored as a JSON payload so the shape can evolve after operator interviews
    without a schema migration.
    """

    __tablename__ = "pricing_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(120), default="demo-defaults")
    payload: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    __table_args__ = (
        UniqueConstraint("room_id", "stay_date", "run_id", name="uq_reco_room_date_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(48), index=True)

    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    base_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    price_before_bounds: Mapped[float] = mapped_column(Float)
    recommended_price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_multiplier: Mapped[float] = mapped_column(Float, default=1.0)

    explanation: Mapped[str] = mapped_column(Text, default="")
    engine_version: Mapped[str] = mapped_column(String(48), default="v1")
    config_version: Mapped[int] = mapped_column(Integer, default=1)

    features: Mapped[dict] = mapped_column(JSON, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    adjustments: Mapped[list["PricingAdjustment"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="PricingAdjustment.sequence",
    )
    decisions: Mapped[list["OperatorDecision"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="OperatorDecision.created_at",
    )


class PricingAdjustment(Base):
    """One explainable step of the pricing calculation."""

    __tablename__ = "pricing_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_recommendations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    code: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(160))
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    price_before: Mapped[float] = mapped_column(Float)
    price_after: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    is_neutral: Mapped[bool] = mapped_column(Boolean, default=False)

    recommendation: Mapped[PricingRecommendation] = relationship(back_populates="adjustments")


class OperatorDecision(Base):
    __tablename__ = "operator_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_recommendations.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(24), index=True)  # accepted | overridden
    recommended_price: Mapped[float] = mapped_column(Float)
    final_price: Mapped[float] = mapped_column(Float)
    previous_price: Mapped[float] = mapped_column(Float, default=0.0)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str] = mapped_column(String(48), default="v1")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    operator: Mapped[str] = mapped_column(String(80), default="demo-operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    recommendation: Mapped[PricingRecommendation] = relationship(back_populates="decisions")
