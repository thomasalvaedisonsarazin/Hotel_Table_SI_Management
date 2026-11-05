from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime


class StaffRole(StrEnum):
    manager = "manager"
    staff = "staff"


class Channel(StrEnum):
    sms = "sms"
    whatsapp = "whatsapp"


class DeliveryStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    logged = "logged"  # No provider is set up, so the message was written to the log only.
    failed = "failed"
    skipped = "skipped"


class StaffMember(Base, TimestampMixin):
    __tablename__ = "staff_members"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "user_id", name="uq_staff_restaurant_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default=StaffRole.staff.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    phone: Mapped[str | None] = mapped_column(String(16))
    alerts_consented: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_waiter_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_cleaning_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    on_shift: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertDelivery(Base):
    """One message to one person on one channel. Rows are queued first, then sent separately."""

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("alert_id", "member_id", "channel", name="uq_delivery_once"),
        Index("ix_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_deliveries_restaurant_created", "restaurant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("staff_members.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=DeliveryStatus.pending.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    provider_message_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
