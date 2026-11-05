"""Sends alerts by SMS, WhatsApp and the phone app. Alerts queue in the database and are
sent by a separate loop, so a slow or failing provider can never hold up the table engine."""

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

from app.auth.security import create_alert_ack_token
from app.config import settings
from app.models import (
    Alert,
    AlertDelivery,
    AlertStatus,
    AlertType,
    Channel,
    DeliveryStatus,
    DiningTable,
    PushDevice,
    Restaurant,
    StaffMember,
)
from app.services.push import PushSender, get_push_sender

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
        seconds = restaurant.waiter_alert_seconds
        wait = f"{seconds} sec" if seconds < 60 else f"{round(seconds / 60)} min"
        issue = f"has waited {wait} for a waiter"
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
        )
    ).all()
    users_with_app = set(
        db.scalars(
            select(PushDevice.user_id).where(PushDevice.user_id.in_([m.user_id for m in members]))
        )
    )
    queued = 0
    for alert in alerts:
        wanted = [
            m
            for m in members
            if (m.notify_waiter_alerts if alert.type == AlertType.waiter.value
                else m.notify_cleaning_alerts)
        ]  # fmt: skip
        for member in wanted:
            can_message = bool(member.phone and member.alerts_consented)
            channels = [
                channel
                for channel, enabled in (
                    (Channel.sms, can_message and member.notify_sms),
                    (Channel.whatsapp, can_message and member.notify_whatsapp),
                    (Channel.push, member.notify_push and member.user_id in users_with_app),
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
                # Phone app alerts are free, so they don't use up the paid message limit.
                AlertDelivery.channel != Channel.push.value,
                AlertDelivery.sent_at >= now - timedelta(hours=24),
            )
        )
        or 0
    )


def _finish(delivery: AlertDelivery, status: DeliveryStatus, error: str | None = None) -> None:
    delivery.status = status.value
    delivery.error = error


def _still_wanted(member: StaffMember, channel: str) -> bool:
    if not (member.is_active and member.on_shift):
        return False
    if channel == Channel.push.value:
        return member.notify_push
    return bool(member.alerts_consented and member.phone)


def _push_to_user(db: Session, push: PushSender, user_id: int, data: dict[str, str]) -> SendResult:
    """Send to all of someone's phones. It counts as sent if at least one phone took it."""
    devices = db.scalars(select(PushDevice).where(PushDevice.user_id == user_id)).all()
    if not devices:
        return SendResult(ok=False, error="This person has no phone with the app")
    results = []
    for device in devices:
        result = push.send(device.token, data)
        if result.unregistered:
            # The app was uninstalled or reset, so this address will never work again.
            db.delete(device)
        results.append(result)
    delivered = next((r for r in results if r.ok), None)
    if delivered:
        return SendResult(ok=True, message_id=delivered.message_id)
    return SendResult(
        ok=False,
        error=results[-1].error,
        retryable=any(r.retryable for r in results),
    )


def _alert_push_data(
    delivery: AlertDelivery, member: StaffMember, message: AlertMessage
) -> dict[str, str]:
    # FCM data values must all be strings.
    return {
        "kind": "alert",
        "alert_id": str(delivery.alert_id),
        "title": f"Table {message.table}",
        "body": f"{message.restaurant}: table {message.table} {message.issue}",
        "ack_url": f"{settings.PUBLIC_APP_URL.rstrip('/')}/api/v1/alerts/acknowledge-from-phone",
        "ack_token": create_alert_ack_token(member.user_id, delivery.alert_id),
    }


def send_test_push(
    db: Session, push: PushSender, user_id: int, message: AlertMessage
) -> SendResult:
    return _push_to_user(
        db, push, user_id, {"kind": "test", "title": "Test alert", "body": message.body}
    )


def stop_ringing_handled_alerts(db: Session, push: PushSender, now: datetime) -> int:
    """Once one person responds to an alert, every other phone can stop ringing."""
    rows = db.execute(
        select(AlertDelivery, StaffMember.user_id)
        .join(Alert, Alert.id == AlertDelivery.alert_id)
        .join(StaffMember, StaffMember.id == AlertDelivery.member_id)
        .where(
            AlertDelivery.channel == Channel.push.value,
            AlertDelivery.status == DeliveryStatus.sent.value,
            AlertDelivery.push_cancelled_at.is_(None),
            Alert.status != AlertStatus.open.value,
        )
        .limit(BATCH_SIZE)
    ).all()
    for delivery, user_id in rows:
        # Not retried: if this is lost, the phone still stops by itself after a few minutes.
        _push_to_user(db, push, user_id, {"kind": "cancel", "alert_id": str(delivery.alert_id)})
        delivery.push_cancelled_at = now
        db.commit()
    return len(rows)


def dispatch_pending(
    db: Session, provider: Provider, now: datetime, push: PushSender | None = None
) -> int:
    """Send what's due. Commits after each message so a crash can't resend the whole batch."""
    push = push or get_push_sender()
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
        is_push = delivery.channel == Channel.push.value
        if alert.status == AlertStatus.resolved.value:
            _finish(delivery, DeliveryStatus.skipped, "Resolved before it was sent")
        elif is_push and alert.status == AlertStatus.acknowledged.value:
            _finish(delivery, DeliveryStatus.skipped, "Someone had already responded")
        elif now - delivery.created_at > MAX_MESSAGE_AGE:
            _finish(delivery, DeliveryStatus.skipped, "Too old to be useful")
        elif not _still_wanted(member, delivery.channel):
            _finish(delivery, DeliveryStatus.skipped, "Person is no longer receiving alerts")
        elif (
            not is_push
            and messages_used_today(db, restaurant.id, now) >= restaurant.daily_message_limit
        ):
            _finish(delivery, DeliveryStatus.failed, "Daily message limit reached")
            logger.warning("Restaurant %s hit its daily message limit", restaurant.id)
        else:
            message = build_message(restaurant, label, alert.type)
            if is_push:
                data = _alert_push_data(delivery, member, message)
                pushed = _push_to_user(db, push, member.user_id, data)
                result, delivered_status = pushed, push.delivered_status
            else:
                sent = provider.send(Channel(delivery.channel), member.phone or "", message)
                result, delivered_status = sent, provider.delivered_status
            delivery.attempts += 1
            if result.ok:
                _finish(delivery, delivered_status)
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
