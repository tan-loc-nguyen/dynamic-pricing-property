"""SQLAlchemy domain model.

Grain: the primary pricing entity is **RoomType x StayDate**. Luminous defines
rates by room category and Blue Jay distributes by room type, so a physical
apartment does not receive its own rate. PhysicalRoom exists because units
still drive inventory and occupancy, and so unit-level overrides remain
possible later without a reshape.

Money: every rate field is a **NET rate** (what Luminous receives), never an
OTA/guest-facing price. The two are deliberately not interchangeable.
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


# ---------------------------------------------------------------- portfolio
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

    room_types: Mapped[list["RoomType"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )


class RoomType(Base):
    """A sellable room category — the unit of pricing.

    ``category`` is the key into the SeasonalRateBook (2br_regular /
    2br_premium / 3br for Luminous).
    """

    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("property_id", "external_id", name="uq_room_type_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(48), index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    units_total: Mapped[int] = mapped_column(Integer, default=1)

    # Legacy fallback only. Live MIN/BASE/MAX come from the SeasonalRateBook;
    # these are the fallback for a room category with no matching rate band.
    fallback_base_net_rate: Mapped[float] = mapped_column(Float, default=2_000_000.0)
    fallback_min_net_rate: Mapped[float] = mapped_column(Float, default=1_500_000.0)
    fallback_max_net_rate: Mapped[float] = mapped_column(Float, default=4_000_000.0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    property: Mapped[Property] = relationship(back_populates="room_types")
    physical_rooms: Mapped[list["PhysicalRoom"]] = relationship(
        back_populates="room_type", cascade="all, delete-orphan"
    )
    inventory: Mapped[list["StayDateInventory"]] = relationship(
        back_populates="room_type", cascade="all, delete-orphan"
    )


class PhysicalRoom(Base):
    """One physical apartment.

    Drives inventory and occupancy. Deliberately does NOT carry a rate: units
    inherit their room type's price. The table exists so unit-level overrides
    can be added later without reshaping the model.
    """

    __tablename__ = "physical_rooms"
    __table_args__ = (UniqueConstraint("room_type_id", "unit_label", name="uq_unit_label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    unit_label: Mapped[str] = mapped_column(String(48))
    floor: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")

    room_type: Mapped[RoomType] = relationship(back_populates="physical_rooms")


# ------------------------------------------------------- validated rate book
class SeasonalRateBand(Base):
    """CLIENT-VALIDATED seasonal MIN/BASE/MAX NET rates.

    This is operator-supplied business fact, not a modelling assumption. It is
    a lookup table, deliberately NOT something the engine derives or multiplies
    a seasonality factor against.
    """

    __tablename__ = "seasonal_rate_bands"
    __table_args__ = (
        UniqueConstraint("season_key", "room_category", name="uq_band_season_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season_key: Mapped[str] = mapped_column(String(48), index=True)
    season_label: Mapped[str] = mapped_column(String(120))
    months: Mapped[list] = mapped_column(JSON)  # e.g. [11, 12, 1]
    room_category: Mapped[str] = mapped_column(String(48), index=True)

    min_net_rate: Mapped[float] = mapped_column(Float)
    base_net_rate: Mapped[float] = mapped_column(Float)
    max_net_rate: Mapped[float] = mapped_column(Float)

    currency: Mapped[str] = mapped_column(String(8), default="VND")
    rate_basis: Mapped[str] = mapped_column(String(16), default="NET")
    source: Mapped[str] = mapped_column(String(32), default="CLIENT_VALIDATED")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ----------------------------------------------------------------- operations
class StayDateInventory(Base):
    """One room type on one stay date: the atomic unit that gets priced."""

    __tablename__ = "stay_date_inventory"
    __table_args__ = (
        UniqueConstraint("room_type_id", "stay_date", name="uq_inventory_room_type_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    units_total: Mapped[int] = mapped_column(Integer, default=1)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)

    # What Luminous currently receives for this date, where known.
    current_net_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Guest-facing price, only when genuinely available. Never derived.
    current_ota_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    season_key: Mapped[str | None] = mapped_column(String(48), nullable=True)

    historical_occupancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_avg_net_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(32), default="mock")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    room_type: Mapped[RoomType] = relationship(back_populates="inventory")

    @property
    def occupancy(self) -> float | None:
        if not self.units_total:
            return None
        return round(self.units_sold / self.units_total, 4)

    @property
    def units_available(self) -> int:
        return max(self.units_total - self.units_sold, 0)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), index=True)
    physical_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("physical_rooms.id", ondelete="SET NULL"), nullable=True
    )
    stay_date: Mapped[date] = mapped_column(Date, index=True)
    booked_at: Mapped[date] = mapped_column(Date, index=True)
    nights: Mapped[int] = mapped_column(Integer, default=1)
    guests: Mapped[int] = mapped_column(Integer, default=2)

    net_rate: Mapped[float] = mapped_column(Float, default=0.0)
    channel: Mapped[str] = mapped_column(String(48), default="Airbnb")
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    source: Mapped[str] = mapped_column(String(32), default="mock")

    @property
    def lead_time_days(self) -> int:
        return max((self.stay_date - self.booked_at).days, 0)


# --------------------------------------------------------------------- events
class Event(Base):
    """A known exceptional-demand date. Manually curated."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    impact_level: Mapped[str] = mapped_column(String(24), default="medium")  # low|medium|high
    # Optional explicit override; when null the configured per-level value is used.
    adjustment_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), default="other")
    source: Mapped[str] = mapped_column(String(80), default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def covers(self, day: date) -> bool:
        return self.is_active and self.start_date <= day <= self.end_date


# --------------------------------------------------------------- market data
class Competitor(Base):
    """A deliberately-selected comparable property (the comp set)."""

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    location: Mapped[str] = mapped_column(String(160), default="")
    comparable_category: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    observations: Mapped[list["MarketObservation"]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan"
    )


# Confidence in an observation as evidence about a comparable rate.
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNUSABLE = "UNUSABLE"
CONFIDENCE_ORDER = {CONFIDENCE_UNUSABLE: 0, CONFIDENCE_LOW: 1, CONFIDENCE_MEDIUM: 2, CONFIDENCE_HIGH: 3}


class MarketObservation(Base):
    """One observed competitor price, with the provenance needed to judge it.

    A price without its basis (taxes? refundable? which LOS? which date?) is
    not comparable to a Luminous NET rate, so the metadata is first-class and
    drives the confidence level.
    """

    __tablename__ = "market_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    room_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("room_types.id", ondelete="CASCADE"), nullable=True, index=True
    )
    competitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"), nullable=True, index=True
    )

    stay_date: Mapped[date] = mapped_column(Date, index=True)
    competitor_name: Mapped[str] = mapped_column(String(160))
    observed_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="VND")

    # --- comparability metadata ---------------------------------------
    room_category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    length_of_stay: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_basis: Mapped[str] = mapped_column(String(24), default="UNKNOWN")  # NET|OTA_SELL|UNKNOWN
    tax_inclusion: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    fee_inclusion: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    promotion_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    is_refundable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    confidence: Mapped[str] = mapped_column(String(16), default=CONFIDENCE_LOW, index=True)
    confidence_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(48), default="mock")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    competitor: Mapped[Competitor | None] = relationship(back_populates="observations")


# ------------------------------------------------------------- configuration
class PricingConfiguration(Base):
    """Versioned snapshot of the EXPERIMENTAL dynamic strategy.

    The client-validated rate book lives in ``seasonal_rate_bands`` and is
    deliberately kept out of this payload so validated fact and unvalidated
    experiment are never mixed.
    """

    __tablename__ = "pricing_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(120), default="demo-defaults")
    payload: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ----------------------------------------------------------- recommendations
class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    __table_args__ = (
        UniqueConstraint("room_type_id", "stay_date", "run_id", name="uq_reco_room_type_date_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(48), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="shadow", index=True)

    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    # --- rate band snapshot (validated input at time of recommendation) ---
    season_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    band_min_net_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_base_net_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_max_net_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    base_net_rate: Mapped[float] = mapped_column(Float)
    current_net_rate: Mapped[float] = mapped_column(Float)
    net_rate_before_clamp: Mapped[float] = mapped_column(Float)
    recommended_net_rate: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_adjustment_pct: Mapped[float] = mapped_column(Float, default=0.0)

    engine_version: Mapped[str] = mapped_column(String(48), default="1.0.0")
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
    outcomes: Mapped[list["RecommendationOutcome"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )


class PricingAdjustment(Base):
    """One explainable step of the calculation.

    The engine is additive: ``adjustment_pct`` is the contribution in
    percentage points.

    ``label_key`` + ``params`` are what make the step translatable: the row
    stores the message key and the figures it interpolates, never a finished
    sentence. ``label`` is the English fallback, and the only text shown for a
    band an operator named themselves (``label_key`` is then NULL).
    """

    __tablename__ = "pricing_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_recommendations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    code: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(200))

    adjustment_pct: Mapped[float] = mapped_column(Float, default=0.0)
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    price_before: Mapped[float] = mapped_column(Float)
    price_after: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float, default=0.0)

    label_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    is_neutral: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False)

    recommendation: Mapped[PricingRecommendation] = relationship(back_populates="adjustments")


class OperatorDecision(Base):
    __tablename__ = "operator_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_recommendations.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(24), index=True)
    recommended_net_rate: Mapped[float] = mapped_column(Float)
    final_net_rate: Mapped[float] = mapped_column(Float)
    previous_net_rate: Mapped[float] = mapped_column(Float, default=0.0)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str] = mapped_column(String(48), default="1.0.0")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    operator: Mapped[str] = mapped_column(String(80), default="demo-operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    recommendation: Mapped[PricingRecommendation] = relationship(back_populates="decisions")


class RecommendationOutcome(Base):
    """What actually happened after a recommendation.

    Empty in production until real post-stay data arrives. Demo outcomes are
    flagged ``is_synthetic`` so they can never be mistaken for measurement.
    """

    __tablename__ = "recommendation_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_recommendations.id", ondelete="CASCADE"), index=True
    )
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id", ondelete="CASCADE"), index=True)
    stay_date: Mapped[date] = mapped_column(Date, index=True)

    units_booked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_occupancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_net_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    cancellations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_booking_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(48), default="demo")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation: Mapped[PricingRecommendation] = relationship(back_populates="outcomes")
