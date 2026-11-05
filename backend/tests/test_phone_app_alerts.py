import base64
import json
from datetime import timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.auth.security import create_access_token, create_alert_ack_token
from app.config import Settings
from app.models import Alert, AlertDelivery, Channel, PushDevice, StaffMember
from app.models.base import utcnow
from app.services import engine_loop, notifications
from app.services.notifications import dispatch_pending, stop_ringing_handled_alerts
from app.services.push import FcmPushSender, LogPushSender, PushResult
from tests.test_staff_and_alerts import FakeProvider, add_staff, base, staff_login

TOKEN = "phone-token-abcdefghijklmnop"
ACK_URL = "/api/v1/alerts/acknowledge-from-phone"


class FakePush:
    name = "fake"
    delivered_status = notifications.DeliveryStatus.sent
    configured = True

    def __init__(self, results=None):
        self.sent = []
        self.results = list(results or [])

    def send(self, token, data):
        self.sent.append((token, data))
        return self.results.pop(0) if self.results else PushResult(ok=True, message_id="m1")


@pytest.fixture
def app_waiter(client, auth, restaurant_id):
    """A waiter with the app on their phone, but no phone number or message alerts."""
    created = add_staff(client, auth, restaurant_id).json()
    headers = staff_login(client, "waiter@example.com", created["temporary_password"])
    assert client.post("/api/v1/devices", json={"token": TOKEN}, headers=headers).status_code == 204
    return created, headers


def raise_alert(db, client, auth, restaurant_id, table_id):
    client.post(
        f"{base(restaurant_id)}/tables/{table_id}/actions", json={"action": "seat"}, headers=auth
    )
    future = utcnow() + timedelta(seconds=301)
    engine_loop.tick(db, future)
    return future


def deliveries(db):
    db.expire_all()
    return db.scalars(select(AlertDelivery)).all()


def test_alert_rings_the_app_without_a_phone_number(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    assert [d.channel for d in deliveries(db)] == [Channel.push.value]

    push = FakePush()
    assert dispatch_pending(db, FakeProvider(), now, push) == 1
    assert dispatch_pending(db, FakeProvider(), now, push) == 0

    token, data = push.sent[0]
    assert token == TOKEN
    assert data["kind"] == "alert"
    assert data["title"] == "Table T1"
    assert "waited 5 min for a waiter" in data["body"]
    assert all(isinstance(value, str) for value in data.values())


@pytest.mark.parametrize(
    "changes", [{"on_shift": False}, {"notify_push": False}], ids=["off shift", "turned off"]
)
def test_no_ring_when_off_shift_or_turned_off(
    client, auth, restaurant_id, table_id, app_waiter, db, changes
):
    _, headers = app_waiter
    client.patch(f"{base(restaurant_id)}/me/alerts", json=changes, headers=headers)
    raise_alert(db, client, auth, restaurant_id, table_id)
    assert deliveries(db) == []


def test_going_off_shift_after_queueing_stops_the_ring(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    _, headers = app_waiter
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    client.patch(f"{base(restaurant_id)}/me/alerts", json={"on_shift": False}, headers=headers)
    push = FakePush()
    dispatch_pending(db, FakeProvider(), now, push)
    assert push.sent == []
    assert deliveries(db)[0].status == "skipped"


def test_no_ring_once_someone_has_responded(client, auth, restaurant_id, table_id, app_waiter, db):
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    alert = db.scalar(select(Alert))
    client.post(f"{base(restaurant_id)}/alerts/{alert.id}/acknowledge", headers=auth)
    db.expire_all()
    push = FakePush()
    dispatch_pending(db, FakeProvider(), now, push)
    assert push.sent == []
    assert deliveries(db)[0].error == "Someone had already responded"


def test_app_alerts_do_not_use_the_paid_message_limit(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    client.patch(base(restaurant_id), json={"daily_message_limit": 1}, headers=auth)
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    dispatch_pending(db, FakeProvider(), now, FakePush())
    assert deliveries(db)[0].status == "sent"
    assert notifications.messages_used_today(db, restaurant_id, now) == 0


def test_temporary_failure_retries_and_uninstalled_app_is_forgotten(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    push = FakePush([PushResult(ok=False, error="Could not reach Firebase", retryable=True)])
    dispatch_pending(db, FakeProvider(), now, push)
    assert deliveries(db)[0].status == "pending"

    later = now + timedelta(seconds=31)
    push = FakePush([PushResult(ok=False, error="Gone", unregistered=True)])
    dispatch_pending(db, FakeProvider(), later, push)
    assert deliveries(db)[0].status == "failed"
    assert db.scalars(select(PushDevice)).all() == []


def test_one_response_stops_every_phone_once(client, auth, restaurant_id, table_id, app_waiter, db):
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    push = FakePush()
    dispatch_pending(db, FakeProvider(), now, push)
    assert stop_ringing_handled_alerts(db, push, now) == 0

    alert = db.scalar(select(Alert))
    client.post(f"{base(restaurant_id)}/alerts/{alert.id}/acknowledge", headers=auth)
    db.expire_all()
    assert stop_ringing_handled_alerts(db, push, now) == 1
    assert push.sent[-1] == (TOKEN, {"kind": "cancel", "alert_id": str(alert.id)})
    assert stop_ringing_handled_alerts(db, push, now) == 0


# Acknowledging from the ringing phone


def ack_token_from_alert(db, client, auth, restaurant_id, table_id):
    now = raise_alert(db, client, auth, restaurant_id, table_id)
    push = FakePush()
    dispatch_pending(db, FakeProvider(), now, push)
    return push.sent[0][1]["ack_token"]


def test_acknowledge_button_works_without_a_login(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    token = ack_token_from_alert(db, client, auth, restaurant_id, table_id)
    assert client.post(ACK_URL, json={"token": token}).status_code == 204
    alert = db.scalar(select(Alert))
    db.refresh(alert)
    assert alert.status == "acknowledged"
    # Pressing it twice, or on two phones, is fine.
    assert client.post(ACK_URL, json={"token": token}).status_code == 204


def test_acknowledge_token_only_does_that_one_thing(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    token = ack_token_from_alert(db, client, auth, restaurant_id, table_id)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    access = create_access_token(app_waiter[0]["user_id"])
    assert client.post(ACK_URL, json={"token": access}).status_code == 401
    assert client.post(ACK_URL, json={"token": "not-a-token"}).status_code == 401


def test_acknowledge_refused_after_removal_or_for_outsiders(
    client, auth, restaurant_id, table_id, app_waiter, db
):
    created, _ = app_waiter
    token = ack_token_from_alert(db, client, auth, restaurant_id, table_id)
    client.patch(
        f"{base(restaurant_id)}/staff/{created['id']}", json={"is_active": False}, headers=auth
    )
    assert client.post(ACK_URL, json={"token": token}).status_code == 401
    alert = db.scalar(select(Alert))
    assert alert.status == "open"
    missing = create_alert_ack_token(created["user_id"], 999_999)
    assert client.post(ACK_URL, json={"token": missing}).status_code == 401


# Registering phones


def test_shared_phone_follows_whoever_signed_in_last(client, auth, app_waiter, db):
    assert client.post("/api/v1/devices", json={"token": TOKEN}, headers=auth).status_code == 204
    devices = db.scalars(select(PushDevice)).all()
    assert len(devices) == 1
    assert devices[0].user_id != app_waiter[0]["user_id"]


def test_only_your_own_phone_can_be_removed(client, auth, app_waiter, db):
    _, headers = app_waiter
    client.post("/api/v1/devices/unregister", json={"token": TOKEN}, headers=auth)
    assert len(db.scalars(select(PushDevice)).all()) == 1
    client.post("/api/v1/devices/unregister", json={"token": TOKEN}, headers=headers)
    db.expire_all()
    assert db.scalars(select(PushDevice)).all() == []


def test_old_phones_are_dropped_past_the_limit(client, auth, db):
    for number in range(7):
        response = client.post(
            "/api/v1/devices", json={"token": f"{TOKEN}-{number}"}, headers=auth
        )
        assert response.status_code == 204
    tokens = set(db.scalars(select(PushDevice.token)))
    assert len(tokens) == 5
    assert f"{TOKEN}-6" in tokens
    assert f"{TOKEN}-0" not in tokens


def test_device_registration_needs_a_login(client):
    assert client.post("/api/v1/devices", json={"token": TOKEN}).status_code == 401


def test_managers_can_see_who_has_the_app_and_test_it(
    client, auth, restaurant_id, app_waiter
):
    created, _ = app_waiter
    listed = client.get(f"{base(restaurant_id)}/staff", headers=auth).json()
    assert listed[0]["push_devices"] == 1

    url = f"{base(restaurant_id)}/staff/{created['id']}/test-alert"
    results = client.post(url, headers=auth).json()
    assert results == [{"channel": "push", "status": "logged", "error": None}]


def test_test_alert_needs_some_way_to_reach_the_person(client, auth, restaurant_id):
    created = add_staff(client, auth, restaurant_id).json()
    url = f"{base(restaurant_id)}/staff/{created['id']}/test-alert"
    assert client.post(url, headers=auth).status_code == 409


def test_notification_status_reports_app_alerts_are_not_set_up(client, auth, restaurant_id):
    status = client.get(f"{base(restaurant_id)}/notifications", headers=auth).json()
    assert status["can_send_push"] is False


def test_member_row_defaults_to_ringing(client, auth, restaurant_id, app_waiter, db):
    assert db.scalar(select(StaffMember)).notify_push is True


# The Firebase request itself, against a fake server


@pytest.fixture(scope="module")
def account():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return (
        {
            "project_id": "dineops-test",
            "client_email": "sender@dineops-test.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        public,
    )


def fcm_sender(account, send_status=200, token_status=200):
    calls = {"token": 0, "send": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            calls["token"] += 1
            calls["assertion"] = dict(httpx.QueryParams(request.content.decode()))
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        calls["send"].append(request)
        if send_status != 200:
            return httpx.Response(send_status, json={"error": {"status": "X"}})
        return httpx.Response(200, json={"name": "projects/dineops-test/messages/1"})

    sender = FcmPushSender(account[0], httpx.Client(transport=httpx.MockTransport(handler)))
    return sender, calls


def test_firebase_request_format(account):
    sender, calls = fcm_sender(account)
    result = sender.send(TOKEN, {"kind": "alert", "title": "Table 4"})
    assert result.ok

    request = calls["send"][0]
    assert str(request.url) == "https://fcm.googleapis.com/v1/projects/dineops-test/messages:send"
    assert request.headers["authorization"] == "Bearer at"
    message = json.loads(request.content)["message"]
    assert message["token"] == TOKEN
    assert message["android"]["priority"] == "HIGH"
    assert message["data"]["kind"] == "alert"
    # A "notification" section would make Android show a quiet alert instead of ringing.
    assert "notification" not in message

    assertion = calls["assertion"]
    assert assertion["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    claims = jwt.decode(
        assertion["assertion"],
        account[1],
        algorithms=["RS256"],
        audience="https://oauth2.googleapis.com/token",
    )
    assert claims["iss"] == account[0]["client_email"]
    assert claims["scope"].endswith("/firebase.messaging")


def test_firebase_login_is_reused(account):
    sender, calls = fcm_sender(account)
    sender.send(TOKEN, {"kind": "alert"})
    sender.send(TOKEN, {"kind": "alert"})
    assert calls["token"] == 1
    assert len(calls["send"]) == 2


@pytest.mark.parametrize(
    ("status", "retryable", "unregistered"),
    [
        (404, False, True),
        (429, True, False),
        (503, True, False),
        (401, True, False),
        (403, False, False),
    ],
)
def test_firebase_errors_are_sorted(account, status, retryable, unregistered):
    sender, _ = fcm_sender(account, send_status=status)
    result = sender.send(TOKEN, {"kind": "alert"})
    assert not result.ok
    assert result.retryable is retryable
    assert result.unregistered is unregistered


def test_firebase_refused_login_is_reported(account):
    sender, _ = fcm_sender(account, token_status=400)
    result = sender.send(TOKEN, {"kind": "alert"})
    assert result.error == "Firebase refused the server's login"
    assert result.retryable is False


def test_firebase_unreachable_is_retried(account):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    sender = FcmPushSender(account[0], httpx.Client(transport=httpx.MockTransport(handler)))
    assert sender.send(TOKEN, {"kind": "alert"}).retryable is True


def test_nothing_is_sent_until_firebase_is_set_up():
    sender = LogPushSender()
    assert sender.configured is False
    assert sender.send(TOKEN, {"kind": "alert"}).ok is True


def settings_with(**values):
    return Settings(DATABASE_URL="sqlite://", SECRET_KEY="k" * 32, **values)


def test_bad_firebase_settings_stop_the_server_starting(account):
    good = base64.b64encode(json.dumps(account[0]).encode()).decode()
    assert settings_with(
        FIREBASE_SERVICE_ACCOUNT_B64=good, PUBLIC_APP_URL="https://app.example.com"
    ).firebase_service_account
    with pytest.raises(ValueError, match="PUBLIC_APP_URL"):
        settings_with(FIREBASE_SERVICE_ACCOUNT_B64=good)
    with pytest.raises(ValueError, match="service account"):
        settings_with(FIREBASE_SERVICE_ACCOUNT_B64="not base64!", PUBLIC_APP_URL="https://a.b")
    wrong = base64.b64encode(b'{"project_id": "x"}').decode()
    with pytest.raises(ValueError, match="service account"):
        settings_with(FIREBASE_SERVICE_ACCOUNT_B64=wrong, PUBLIC_APP_URL="https://a.b")
