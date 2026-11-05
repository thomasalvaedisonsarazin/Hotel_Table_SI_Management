"""Sends alerts by SMS and WhatsApp. Alerts queue in the database and are sent by a separate loop,
so a slow or failing provider can never hold up the table engine."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Alert,
    AlertDelivery,
    AlertStatus,
    AlertType,
    Channel,
    DeliveryStatus,
    DiningTable,
    Restaurant,
    StaffMember,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 30
# A "table 4 needs a waiter" text is useless after this long, so don't send it late.
MAX_MESSAGE_AGE = timedelta(minutes=10)
BATCH_SIZE = 25


@dataclass
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None
    retryable: bool = False


@dataclass
class AlertMessage:
    restaurant: str
    table: str
    issue: str

    @property
    def body(self) -> str:
        return f"{settings.APP_NAME}: {self.restaurant}, table {self.table} {self.issue}."


class Provider(Protocol):
    name: str
    delivered_status: DeliveryStatus

    def can_send(self, channel: Channel) -> bool: ...

    def send(self, channel: Channel, to: str, message: AlertMessage) -> SendResult: ...


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}******{phone[-2:]}"


class LogProvider:
    """Used until real sending is set up. Nothing leaves the server."""

    name = "log"
    delivered_status = DeliveryStatus.logged

    def can_send(self, channel: Channel) -> bool:
        return False

    def send(self, channel: Channel, to: str, message: AlertMessage) -> SendResult:
        logger.info("Would send %s to %s: %s", channel.value, mask_phone(to), message.body)
        return SendResult(ok=True)


class TwilioProvider:
    name = "twilio"
    delivered_status = DeliveryStatus.sent

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10)
        self._url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"

    def can_send(self, channel: Channel) -> bool:
        if channel is Channel.sms:
            return bool(settings.TWILIO_SMS_FROM)
        return bool(settings.TWILIO_WHATSAPP_FROM)

    def _payload(self, channel: Channel, to: str, message: AlertMessage) -> dict[str, str]:
        if channel is Channel.sms:
            return {"From": settings.TWILIO_SMS_FROM, "To": to, "Body": message.body}
        payload = {"From": f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}", "To": f"whatsapp:{to}"}
        if settings.TWILIO_WHATSAPP_CONTENT_SID:
            # WhatsApp only allows an approved template when the business messages first.
            payload["ContentSid"] = settings.TWILIO_WHATSAPP_CONTENT_SID
            payload["ContentVariables"] = json.dumps(
                {"1": message.restaurant, "2": message.table, "3": message.issue}
            )
        else:
            payload["Body"] = message.body
        return payload

    def send(self, channel: Channel, to: str, message: AlertMessage) -> SendResult:
        if not self.can_send(channel):
            return SendResult(ok=False, error=f"No {channel.value} sender is set up")
        try:
            response = self._client.post(
                self._url,
                data=self._payload(channel, to, message),
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
        except httpx.HTTPError as exc:
            logger.warning("Twilio request failed: %s", type(exc).__name__)
            return SendResult(ok=False, error="Could not reach Twilio", retryable=True)

        if response.status_code in (200, 201):
            return SendResult(ok=True, message_id=str(response.json().get("sid", ""))[:64])

        retryable = response.status_code == 429 or response.status_code >= 500
        try:
            detail = response.json()
            error = f"Twilio error {detail.get('code')}: {detail.get('message')}"
        except ValueError:
            error = f"Twilio returned HTTP {response.status_code}"
        logger.warning("Twilio rejected a message with HTTP %s", response.status_code)
        return SendResult(ok=False, error=error[:200], retryable=retryable)


@lru_cache
def get_provider() -> Provider:
    return TwilioProvider() if settings.NOTIFICATION_PROVIDER == "twilio" else LogProvider()


def build_message(restaurant: Restaurant, table_label: str, alert_type: str) -> AlertMessage:
    if alert_type == AlertType.waiter.value:
        minutes = max(1, round(restaurant.waiter_alert_seconds / 60))
        issue = f"has waited {minutes} min for a waiter"
    else:
        issue = "is waiting to be cleaned"
    return AlertMessage(restaurant=restaurant.name, table=table_label, issue=issue)


def queue_alert_messages(
    db: Session, restaurant: Restaurant, alerts: list[Alert], now: datetime
) -> int:
    """Queue messages for new alerts. Demo restaurants never message anyone: their simulator
    raises alerts constantly and would run up a real bill."""
    if restaurant.is_demo or not alerts:
        return 0
    members = db.scalars(
        select(StaffMember).where(
            StaffMember.restaurant_id == restaurant.id,
            StaffMember.is_active.is_(True),
            StaffMember.on_shift.is_(True),
            StaffMember.alerts_consented.is_(True),
            StaffMember.phone.is_not(None),
        )
    ).all()
    queued = 0
    for alert in alerts:
        wanted = [
            m
            for m in members
            if (m.notify_waiter_alerts if alert.type == AlertType.waiter.value
                else m.notify_cleaning_alerts)
        ]  # fmt: skip
        for member in wanted:
            channels = [
                channel
                for channel, enabled in (
                    (Channel.sms, member.notify_sms),
                    (Channel.whatsapp, member.notify_whatsapp),
                )
                if enabled
            ]
            for channel in channels:
                delivery = AlertDelivery(
                    restaurant_id=restaurant.id,
                    alert_id=alert.id,
                    member_id=member.id,
                    channel=channel.value,
                    status=DeliveryStatus.pending.value,
                    next_attempt_at=now,
                    created_at=now,
                )
                try:
                    with db.begin_nested():
                        db.add(delivery)
                except IntegrityError:
                    continue
                queued += 1
    return queued


def messages_used_today(db: Session, restaurant_id: int, now: datetime) -> int:
    return (
        db.scalar(
            select(func.count(AlertDelivery.id)).where(
                AlertDelivery.restaurant_id == restaurant_id,
                AlertDelivery.status == DeliveryStatus.sent.value,
                AlertDelivery.sent_at >= now - timedelta(hours=24),
            )
        )
        or 0
    )


def _finish(delivery: AlertDelivery, status: DeliveryStatus, error: str | None = None) -> None:
    delivery.status = status.value
    delivery.error = error


def dispatch_pending(db: Session, provider: Provider, now: datetime) -> int:
    """Send what's due. Commits after each message so a crash can't resend the whole batch."""
    rows = db.execute(
        select(AlertDelivery, Alert, StaffMember, Restaurant, DiningTable.label)
        .join(Alert, Alert.id == AlertDelivery.alert_id)
        .join(StaffMember, StaffMember.id == AlertDelivery.member_id)
        .join(Restaurant, Restaurant.id == AlertDelivery.restaurant_id)
        .join(DiningTable, DiningTable.id == Alert.table_id)
        .where(
            AlertDelivery.status == DeliveryStatus.pending.value,
            AlertDelivery.next_attempt_at <= now,
        )
        .order_by(AlertDelivery.next_attempt_at, AlertDelivery.id)
        .limit(BATCH_SIZE)
    ).all()

    delivered = 0
    for delivery, alert, member, restaurant, label in rows:
        if alert.status == AlertStatus.resolved.value:
            _finish(delivery, DeliveryStatus.skipped, "Resolved before it was sent")
        elif now - delivery.created_at > MAX_MESSAGE_AGE:
            _finish(delivery, DeliveryStatus.skipped, "Too old to be useful")
        elif not (
            member.is_active and member.on_shift and member.alerts_consented and member.phone
        ):
            _finish(delivery, DeliveryStatus.skipped, "Person is no longer receiving alerts")
        elif messages_used_today(db, restaurant.id, now) >= restaurant.daily_message_limit:
            _finish(delivery, DeliveryStatus.failed, "Daily message limit reached")
            logger.warning("Restaurant %s hit its daily message limit", restaurant.id)
        else:
            result = provider.send(
                Channel(delivery.channel),
                member.phone,
                build_message(restaurant, label, alert.type),
            )
            delivery.attempts += 1
            if result.ok:
                _finish(delivery, provider.delivered_status)
                delivery.sent_at = now
                delivery.provider_message_id = result.message_id
                delivered += 1
            elif result.retryable and delivery.attempts < MAX_ATTEMPTS:
                delivery.error = result.error
                delivery.next_attempt_at = now + timedelta(
                    seconds=RETRY_BASE_SECONDS * 2 ** (delivery.attempts - 1)
                )
            else:
                _finish(delivery, DeliveryStatus.failed, result.error)
        db.commit()
    return delivered
