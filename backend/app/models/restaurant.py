from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, utcnow


class TableStatus(StrEnum):
    free = "free"
    occupied = "occupied"
    needs_cleaning = "needs_cleaning"


class AlertType(StrEnum):
    waiter = "waiter"
    cleaning = "cleaning"


class AlertStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class WaitlistStatus(StrEnum):
    waiting = "waiting"
    seated = "seated"
    left = "left"


class Restaurant(Base, TimestampMixin):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    simulator_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    waiter_alert_seconds: Mapped[int] = mapped_column(Integer, default=300)
    cleaning_alert_seconds: Mapped[int] = mapped_column(Integer, default=120)
    seat_confirm_seconds: Mapped[int] = mapped_column(Integer, default=30)
    vacate_confirm_seconds: Mapped[int] = mapped_column(Integer, default=90)
    service_confirm_seconds: Mapped[int] = mapped_column(Integer, default=10)
    clean_confirm_seconds: Mapped[int] = mapped_column(Integer, default=30)
    default_turn_minutes: Mapped[int] = mapped_column(Integer, default=45)
    covers_per_waiter: Mapped[int] = mapped_column(Integer, default=20)


class DiningTable(Base, TimestampMixin):
    __tablename__ = "dining_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(20))
    seats: Mapped[int] = mapped_column(Integer, default=4)
    x: Mapped[float] = mapped_column(Float, default=10.0)
    y: Mapped[float] = mapped_column(Float, default=10.0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default=TableStatus.free.value)
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    guests_first_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    guests_last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    staff_first_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class TableSession(Base):
    """One party's stay at a table, from sitting down until the table is reset."""

    __tablename__ = "table_sessions"
    __table_args__ = (
        Index("ix_sessions_table_cleaned", "table_id", "cleaned_at"),
        Index("ix_sessions_restaurant_seated", "restaurant_id", "seated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id", ondelete="CASCADE"))
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    seated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    first_served_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    vacated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cleaned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("session_id", "type", name="uq_alert_session_type"),
        Index("ix_alerts_restaurant_status", "restaurant_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id", ondelete="CASCADE"))
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=AlertStatus.open.value)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (Index("ix_waitlist_restaurant_status", "restaurant_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("dining_tables.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(80))
    party_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=WaitlistStatus.waiting.value)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)
    seated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
