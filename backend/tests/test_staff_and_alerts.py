from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.models import Alert, AlertDelivery, DiningTable, StaffMember, User
from app.models.base import utcnow
from app.services import engine_loop, notifications
from app.services.notifications import (
    AlertMessage,
    LogProvider,
    SendResult,
    TwilioProvider,
    dispatch_pending,
    mask_phone,
)
from tests.conftest import register_and_login

PHONE = "+919876543210"


def base(restaurant_id: int) -> str:
    return f"/api/v1/restaurants/{restaurant_id}"


def add_staff(client, auth, restaurant_id, email="waiter@example.com", **extra):
    payload = {"full_name": "Ravi", "email": email, **extra}
    return client.post(f"{base(restaurant_id)}/staff", json=payload, headers=auth)


def staff_login(client, email, password, new_password="my-new-password-1"):
    """Log in with a temporary password and set a real one. Returns auth headers."""
    tokens = client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    ).json()
    pending = {"Authorization": f"Bearer {tokens['access_token']}"}
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": password, "new_password": new_password},
        headers=pending,
    )
    assert changed.status_code == 200
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}


@pytest.fixture
def waiter(client, auth, restaurant_id):
    created = add_staff(client, auth, restaurant_id).json()
    headers = staff_login(client, "waiter@example.com", created["temporary_password"])
    return created, headers


class FakeProvider:
    name = "fake"
    delivered_status = notifications.DeliveryStatus.sent

    def __init__(self, results=None):
        self.sent = []
        self.results = list(results or [])

    def can_send(self, channel):
        return True

    def send(self, channel, to, message):
        self.sent.append((channel.value, to, message.body))
        return self.results.pop(0) if self.results else SendResult(ok=True, message_id="SM1")


def alert_setup(db, client, auth, restaurant_id, table_id, **member):
    """A consenting waiter with a phone, plus a table that has just raised a waiter alert."""
    settings = {"phone": PHONE, "alerts_consented": True, "notify_whatsapp": True, **member}
    created = add_staff(client, auth, restaurant_id, **settings)
    assert created.status_code == 201
    client.post(
        f"{base(restaurant_id)}/tables/{table_id}/actions", json={"action": "seat"}, headers=auth
    )
    future = utcnow() + timedelta(seconds=301)
    engine_loop.tick(db, future)
    return future


# Temporary passwords and the forced change


def test_temporary_password_is_shown_once_and_only_hashed(client, auth, restaurant_id, db):
    created = add_staff(client, auth, restaurant_id).json()
    assert created["temporary_password"]
    user = db.scalar(select(User).where(User.email == "waiter@example.com"))
    assert created["temporary_password"] not in user.hashed_password
    assert user.must_change_password is True
    listed = client.get(f"{base(restaurant_id)}/staff", headers=auth).json()
    assert "temporary_password" not in listed[0]


def test_temporary_password_blocks_everything_until_changed(client, auth, restaurant_id, table_id):
    created = add_staff(client, auth, restaurant_id).json()
    password = created["temporary_password"]
    tokens = client.post(
        "/api/v1/auth/login", data={"username": "waiter@example.com", "password": password}
    ).json()
    pending = {"Authorization": f"Bearer {tokens['access_token']}"}

    blocked = client.get(f"{base(restaurant_id)}/floor", headers=pending)
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/auth/me", headers=pending).json()["must_change_password"] is True

    with client.websocket_connect(f"/api/v1/ws/restaurants/{restaurant_id}") as socket:
        socket.send_json({"token": tokens["access_token"]})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()

    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "nope-nope-nope", "new_password": "my-new-password-1"},
        headers=pending,
    )
    assert wrong.status_code == 401
    same = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": password, "new_password": password},
        headers=pending,
    )
    assert same.status_code == 409

    fresh = staff_login(client, "waiter@example.com", password)
    assert client.get(f"{base(restaurant_id)}/floor", headers=fresh).status_code == 200
    old = client.post(
        "/api/v1/auth/login", data={"username": "waiter@example.com", "password": password}
    )
    assert old.status_code == 401


# Permissions


def test_staff_can_run_the_floor_but_not_the_business(
    client, auth, restaurant_id, table_id, waiter
):
    _, headers = waiter
    url = base(restaurant_id)
    assert client.get(url, headers=headers).json()["my_role"] == "staff"
    assert client.get(f"{url}/floor", headers=headers).json()["restaurant"]["my_role"] == "staff"
    seat = client.post(f"{url}/tables/{table_id}/actions", json={"action": "seat"}, headers=headers)
    assert seat.status_code == 200
    add = client.post(f"{url}/waitlist", json={"name": "A", "party_size": 2}, headers=headers)
    assert add.status_code == 201

    denied = [
        client.patch(url, json={"name": "Mine now"}, headers=headers),
        client.delete(url, headers=headers),
        client.post(f"{url}/api-key", headers=headers),
        client.post(f"{url}/simulator", json={"enabled": True}, headers=headers),
        client.get(f"{url}/analytics", headers=headers),
        client.post(f"{url}/tables", json={"label": "X"}, headers=headers),
        client.patch(f"{url}/tables/{table_id}", json={"x": 1}, headers=headers),
        client.delete(f"{url}/tables/{table_id}", headers=headers),
        client.get(f"{url}/staff", headers=headers),
        client.post(
            f"{url}/staff", json={"full_name": "B", "email": "b@example.com"}, headers=headers
        ),
        client.get(f"{url}/notifications", headers=headers),
    ]
    assert [r.status_code for r in denied] == [403] * len(denied)


def test_staff_account_cannot_open_restaurants(client, waiter):
    _, headers = waiter
    assert (
        client.post("/api/v1/restaurants", json={"name": "X"}, headers=headers).status_code == 403
    )
    assert client.post("/api/v1/restaurants/demo", json={}, headers=headers).status_code == 403


def test_staff_only_sees_their_own_restaurant(client, auth, restaurant_id, waiter):
    _, headers = waiter
    second = client.post("/api/v1/restaurants", json={"name": "Other"}, headers=auth).json()["id"]
    listed = client.get("/api/v1/restaurants", headers=headers).json()
    assert [r["id"] for r in listed] == [restaurant_id]
    assert client.get(base(second), headers=headers).status_code == 404


def test_manager_can_manage_staff_but_not_managers_or_ownership(
    client, auth, restaurant_id, waiter
):
    waiter_member, _ = waiter
    created = add_staff(client, auth, restaurant_id, "boss@example.com", role="manager").json()
    manager = staff_login(client, "boss@example.com", created["temporary_password"])
    url = base(restaurant_id)

    assert client.get(f"{url}/analytics", headers=manager).status_code == 200
    assert client.patch(url, json={"name": "New"}, headers=manager).status_code == 200
    assert client.get(f"{url}/staff", headers=manager).status_code == 200
    staff_ok = add_staff(client, manager, restaurant_id, "new@example.com")
    assert staff_ok.status_code == 201

    assert (
        add_staff(client, manager, restaurant_id, "m2@example.com", role="manager").status_code
        == 403
    )
    promote = client.patch(
        f"{url}/staff/{waiter_member['id']}", json={"role": "manager"}, headers=manager
    )
    assert promote.status_code == 403
    own = client.patch(f"{url}/staff/{created['id']}", json={"is_active": False}, headers=manager)
    assert own.status_code == 403
    assert client.delete(url, headers=manager).status_code == 403
    assert client.post(f"{url}/api-key", headers=manager).status_code == 403


def test_staff_from_another_restaurant_cannot_be_touched(client, auth, restaurant_id, waiter):
    member, _ = waiter
    other_owner = register_and_login(client, "other@example.com")
    theirs = client.post("/api/v1/restaurants", json={"name": "T"}, headers=other_owner).json()[
        "id"
    ]
    url = f"{base(theirs)}/staff/{member['id']}"
    assert client.patch(url, json={"is_active": False}, headers=other_owner).status_code == 404
    assert client.post(f"{url}/reset-password", headers=other_owner).status_code == 404
    assert client.post(f"{url}/test-alert", headers=other_owner).status_code == 404


def test_cannot_take_over_an_existing_email(client, auth, restaurant_id):
    register_and_login(client, "taken@example.com")
    assert add_staff(client, auth, restaurant_id, "taken@example.com").status_code == 409


# Removing access


def test_deactivating_ends_access_everywhere(client, auth, restaurant_id, waiter):
    member, headers = waiter
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "waiter@example.com", "password": "my-new-password-1"},
    ).json()
    token = headers["Authorization"].split()[1]

    with client.websocket_connect(f"/api/v1/ws/restaurants/{restaurant_id}") as socket:
        socket.send_json({"token": token})
        assert socket.receive_json() == {"type": "ready"}
        response = client.patch(
            f"{base(restaurant_id)}/staff/{member['id']}", json={"is_active": False}, headers=auth
        )
        assert response.status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4401

    assert client.get(f"{base(restaurant_id)}/floor", headers=headers).status_code == 401
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 401
    relogin = client.post(
        "/api/v1/auth/login",
        data={"username": "waiter@example.com", "password": "my-new-password-1"},
    )
    assert relogin.status_code == 401

    again = client.patch(
        f"{base(restaurant_id)}/staff/{member['id']}", json={"is_active": True}, headers=auth
    )
    assert again.json()["is_active"] is True
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": "waiter@example.com", "password": "my-new-password-1"},
        ).status_code
        == 200
    )


def test_reset_password_ends_sessions_and_forces_change(client, auth, restaurant_id, waiter):
    member, _ = waiter
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "waiter@example.com", "password": "my-new-password-1"},
    ).json()
    response = client.post(
        f"{base(restaurant_id)}/staff/{member['id']}/reset-password", headers=auth
    )
    temporary = response.json()["temporary_password"]
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 401
    assert staff_login(client, "waiter@example.com", temporary, "another-password-2")


def test_deleting_restaurant_ends_staff_logins(client, auth, restaurant_id, table_id, waiter, db):
    client.post(
        f"{base(restaurant_id)}/tables/{table_id}/actions", json={"action": "seat"}, headers=auth
    )
    assert client.delete(base(restaurant_id), headers=auth).status_code == 204
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "waiter@example.com", "password": "my-new-password-1"},
    )
    assert login.status_code == 401
    assert db.scalars(select(StaffMember)).all() == []
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200


# Consent


@pytest.mark.parametrize(
    "extra",
    [
        {"notify_sms": True},
        {"notify_sms": True, "phone": PHONE},
        {"notify_whatsapp": True, "phone": PHONE, "alerts_consented": False},
    ],
)
def test_alerts_need_a_phone_and_consent(client, auth, restaurant_id, extra):
    assert add_staff(client, auth, restaurant_id, **extra).status_code == 409


def test_bad_phone_numbers_rejected_and_formatting_cleaned(client, auth, restaurant_id):
    for phone in ("98765", "9876543210", "+0123456789", "+91abc"):
        assert add_staff(client, auth, restaurant_id, phone=phone).status_code == 422
    created = add_staff(client, auth, restaurant_id, phone="+91 98765-43210")
    assert created.json()["phone"] == PHONE


def test_changing_phone_clears_consent_and_channels(client, auth, restaurant_id):
    member = add_staff(
        client, auth, restaurant_id, phone=PHONE, alerts_consented=True, notify_sms=True
    ).json()
    updated = client.patch(
        f"{base(restaurant_id)}/staff/{member['id']}", json={"phone": "+919000000000"}, headers=auth
    ).json()
    assert updated["alerts_consented"] is False
    assert updated["notify_sms"] is False


def test_turning_on_channel_without_consent_conflicts(client, auth, restaurant_id):
    member = add_staff(client, auth, restaurant_id, phone=PHONE).json()
    response = client.patch(
        f"{base(restaurant_id)}/staff/{member['id']}", json={"notify_sms": True}, headers=auth
    )
    assert response.status_code == 409


def test_staff_controls_their_own_alerts(client, auth, restaurant_id, db):
    created = add_staff(client, auth, restaurant_id, phone=PHONE).json()
    headers = staff_login(client, "waiter@example.com", created["temporary_password"])
    url = f"{base(restaurant_id)}/me/alerts"
    assert client.get(url, headers=headers).json()["on_shift"] is True
    updated = client.patch(url, json={"notify_whatsapp": True, "on_shift": False}, headers=headers)
    assert updated.json()["notify_whatsapp"] is True
    assert updated.json()["alerts_consented"] is True
    assert updated.json()["on_shift"] is False
    assert client.get(url, headers=auth).json() is None
    assert client.patch(url, json={"on_shift": False}, headers=auth).status_code == 404


def test_staff_without_phone_cannot_turn_on_alerts(client, waiter, restaurant_id):
    _, headers = waiter
    response = client.patch(
        f"{base(restaurant_id)}/me/alerts", json={"notify_sms": True}, headers=headers
    )
    assert response.status_code == 409


def test_owner_can_get_alerts_on_their_own_phone(client, auth, restaurant_id):
    response = add_staff(
        client, auth, restaurant_id, "owner@example.com", phone=PHONE, alerts_consented=True,
        notify_whatsapp=True,
    )  # fmt: skip
    assert response.status_code == 201
    assert response.json()["temporary_password"] is None
    assert response.json()["is_owner"] is True
    assert client.get(base(restaurant_id), headers=auth).json()["my_role"] == "owner"
    assert client.get("/api/v1/auth/me", headers=auth).json()["must_change_password"] is False
    assert add_staff(client, auth, restaurant_id, "owner@example.com").status_code == 409
    member = response.json()
    ignored = client.patch(
        f"{base(restaurant_id)}/staff/{member['id']}", json={"is_active": False}, headers=auth
    )
    assert ignored.json()["is_active"] is True


# Queueing and sending


def test_alert_queues_only_for_people_who_should_get_it(client, auth, restaurant_id, table_id, db):
    url = base(restaurant_id)
    consent = {"phone": PHONE, "alerts_consented": True, "notify_sms": True}
    add_staff(client, auth, restaurant_id, "a@example.com", **consent)
    add_staff(client, auth, restaurant_id, "both@example.com", **consent, notify_whatsapp=True)
    add_staff(client, auth, restaurant_id, "nophone@example.com")
    add_staff(
        client, auth, restaurant_id, "cleaner@example.com", **consent, notify_waiter_alerts=False
    )
    off = add_staff(client, auth, restaurant_id, "off@example.com", **consent).json()
    client.patch(f"{url}/staff/{off['id']}", json={"on_shift": False}, headers=auth)
    gone = add_staff(client, auth, restaurant_id, "gone@example.com", **consent).json()
    client.patch(f"{url}/staff/{gone['id']}", json={"is_active": False}, headers=auth)

    client.post(f"{url}/tables/{table_id}/actions", json={"action": "seat"}, headers=auth)
    engine_loop.tick(db, utcnow() + timedelta(seconds=301))

    rows = db.scalars(select(AlertDelivery)).all()
    assert sorted(r.channel for r in rows) == ["sms", "sms", "whatsapp"]
    engine_loop.tick(db, utcnow() + timedelta(seconds=400))
    assert len(db.scalars(select(AlertDelivery)).all()) == 3


def test_demo_restaurant_never_queues_or_sends_messages(client, auth, db):
    demo = client.post("/api/v1/restaurants/demo", json={}, headers=auth).json()
    url = base(demo["id"])
    member = client.post(
        f"{url}/staff",
        json={
            "full_name": "W",
            "email": "w@example.com",
            "phone": PHONE,
            "alerts_consented": True,
            "notify_sms": True,
        },
        headers=auth,
    ).json()
    start = utcnow()
    for second in range(0, 300, 2):
        engine_loop.tick(db, start + timedelta(seconds=second))
    assert db.scalars(select(Alert).where(Alert.created_at >= start)).first() is not None
    assert db.scalars(select(AlertDelivery)).all() == []
    assert client.post(f"{url}/staff/{member['id']}/test-alert", headers=auth).status_code == 409


def test_message_is_sent_once_with_useful_text(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    provider = FakeProvider()
    assert dispatch_pending(db, provider, future) == 1
    assert provider.sent == [
        ("whatsapp", PHONE, "DineOps SI: Cafe, table T1 has waited 5 min for a waiter.")
    ]
    delivery = db.scalar(select(AlertDelivery))
    assert delivery.status == "sent"
    assert delivery.provider_message_id == "SM1"
    assert dispatch_pending(db, provider, future + timedelta(seconds=60)) == 0
    assert len(provider.sent) == 1


def test_temporary_failure_retries_then_succeeds(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    provider = FakeProvider([SendResult(ok=False, error="busy", retryable=True)])
    dispatch_pending(db, provider, future)
    delivery = db.scalar(select(AlertDelivery))
    assert delivery.status == "pending"
    assert delivery.attempts == 1
    assert dispatch_pending(db, provider, future + timedelta(seconds=5)) == 0
    assert dispatch_pending(db, provider, future + timedelta(seconds=30)) == 1
    db.refresh(delivery)
    assert delivery.status == "sent"


def test_gives_up_after_three_temporary_failures(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    bad = SendResult(ok=False, error="busy", retryable=True)
    provider = FakeProvider([bad, bad, bad])
    delivery = None
    for seconds in (0, 30, 90):
        dispatch_pending(db, provider, future + timedelta(seconds=seconds))
    delivery = db.scalar(select(AlertDelivery))
    assert delivery.status == "failed"
    assert delivery.attempts == 3
    assert dispatch_pending(db, provider, future + timedelta(seconds=500)) == 0
    assert len(provider.sent) == 3


def test_permanent_failure_does_not_retry(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    provider = FakeProvider([SendResult(ok=False, error="bad number")])
    dispatch_pending(db, provider, future)
    delivery = db.scalar(select(AlertDelivery))
    assert delivery.status == "failed"
    assert delivery.error == "bad number"


def test_no_message_if_problem_already_fixed(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    client.post(
        f"{base(restaurant_id)}/tables/{table_id}/actions", json={"action": "served"}, headers=auth
    )
    provider = FakeProvider()
    dispatch_pending(db, provider, future)
    assert provider.sent == []
    assert db.scalar(select(AlertDelivery)).status == "skipped"


def test_stale_message_is_not_sent(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    provider = FakeProvider()
    dispatch_pending(db, provider, future + timedelta(minutes=11))
    assert provider.sent == []
    assert db.scalar(select(AlertDelivery)).status == "skipped"


def test_going_off_shift_stops_queued_message(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    member = db.scalar(select(StaffMember))
    member.on_shift = False
    db.commit()
    provider = FakeProvider()
    dispatch_pending(db, provider, future)
    assert provider.sent == []


def test_daily_limit_stops_paid_messages(client, auth, restaurant_id, table_id, db):
    client.patch(base(restaurant_id), json={"daily_message_limit": 0}, headers=auth)
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    provider = FakeProvider()
    dispatch_pending(db, provider, future)
    assert provider.sent == []
    delivery = db.scalar(select(AlertDelivery))
    assert delivery.status == "failed"
    assert delivery.error == "Daily message limit reached"


def test_notification_status_and_log_provider_are_honest(client, auth, restaurant_id, table_id, db):
    future = alert_setup(db, client, auth, restaurant_id, table_id)
    dispatch_pending(db, LogProvider(), future)
    data = client.get(f"{base(restaurant_id)}/notifications", headers=auth).json()
    assert data["provider"] == "log"
    assert data["can_send_whatsapp"] is False
    assert data["sent_last_24h"] == 0
    assert data["recent"][0]["status"] == "logged"
    assert data["recent"][0]["table_label"] == "T1"


def test_test_alert_requires_channels_and_reports_result(client, auth, restaurant_id):
    url = base(restaurant_id)
    bare = add_staff(client, auth, restaurant_id, "bare@example.com").json()
    assert client.post(f"{url}/staff/{bare['id']}/test-alert", headers=auth).status_code == 409
    member = add_staff(
        client, auth, restaurant_id, phone=PHONE, alerts_consented=True, notify_sms=True
    ).json()
    response = client.post(f"{url}/staff/{member['id']}/test-alert", headers=auth)
    assert response.json() == [{"channel": "sms", "status": "logged", "error": None}]
    for _ in range(5):
        last = client.post(f"{url}/staff/{member['id']}/test-alert", headers=auth)
    assert last.status_code == 429


def test_table_lookup_and_alert_body_for_cleaning(db, engine_setup):
    restaurant, table = engine_setup
    message = notifications.build_message(restaurant, table.label, "cleaning")
    assert message.body == "DineOps SI: Engine, table T1 is waiting to be cleaned."
    assert db.get(DiningTable, table.id)


def test_short_waiter_limit_is_worded_accurately(db, engine_setup):
    restaurant, table = engine_setup
    restaurant.waiter_alert_seconds = 15
    message = notifications.build_message(restaurant, table.label, "waiter")
    assert message.body == "DineOps SI: Engine, table T1 has waited 15 sec for a waiter."


def test_phone_numbers_are_masked_in_logs(caplog):
    with caplog.at_level("INFO"):
        LogProvider().send(
            notifications.Channel.sms, PHONE, AlertMessage("Cafe", "T1", "needs a waiter")
        )
    assert PHONE not in caplog.text
    assert mask_phone(PHONE) in caplog.text


# Twilio request format, checked against a fake transport. No real messages are sent.


def twilio(handler, monkeypatch, **overrides):
    values = {
        "TWILIO_ACCOUNT_SID": "ACtest",
        "TWILIO_AUTH_TOKEN": "secret-token",
        "TWILIO_SMS_FROM": "+15550000001",
        "TWILIO_WHATSAPP_FROM": "+15550000002",
        "TWILIO_WHATSAPP_CONTENT_SID": "",
        **overrides,
    }
    for key, value in values.items():
        monkeypatch.setattr(notifications.settings, key, value)
    return TwilioProvider(httpx.Client(transport=httpx.MockTransport(handler)))


MESSAGE = AlertMessage("Cafe", "T1", "needs a waiter")


def test_twilio_sms_request(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(201, json={"sid": "SM123"})

    result = twilio(handler, monkeypatch).send(notifications.Channel.sms, PHONE, MESSAGE)
    assert result == SendResult(ok=True, message_id="SM123")
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
    assert "To=%2B919876543210" in seen["body"]
    assert "From=%2B15550000001" in seen["body"]
    assert seen["auth"].startswith("Basic ")


def test_twilio_whatsapp_uses_prefix_and_body(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        return httpx.Response(201, json={"sid": "SM1"})

    twilio(handler, monkeypatch).send(notifications.Channel.whatsapp, PHONE, MESSAGE)
    assert "To=whatsapp%3A%2B919876543210" in seen["body"]
    assert "Body=" in seen["body"]


def test_twilio_whatsapp_uses_template_when_set(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        return httpx.Response(201, json={"sid": "SM1"})

    provider = twilio(handler, monkeypatch, TWILIO_WHATSAPP_CONTENT_SID="HXabc")
    provider.send(notifications.Channel.whatsapp, PHONE, MESSAGE)
    assert "ContentSid=HXabc" in seen["body"]
    assert "ContentVariables=" in seen["body"]
    assert "Body=" not in seen["body"]


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (401, False), (429, True), (500, True), (503, True)]
)
def test_twilio_errors_are_classified(monkeypatch, status, retryable):
    def handler(_):
        return httpx.Response(status, json={"code": 21211, "message": "Invalid To number"})

    result = twilio(handler, monkeypatch).send(notifications.Channel.sms, PHONE, MESSAGE)
    assert result.ok is False
    assert result.retryable is retryable
    assert result.error == "Twilio error 21211: Invalid To number"


def test_twilio_non_json_error_and_network_failure(monkeypatch):
    def not_json(_):
        return httpx.Response(502, text="<html>bad gateway</html>")

    result = twilio(not_json, monkeypatch).send(notifications.Channel.sms, PHONE, MESSAGE)
    assert result.error == "Twilio returned HTTP 502"
    assert result.retryable is True

    def down(request):
        raise httpx.ConnectError("no route to secret-token", request=request)

    result = twilio(down, monkeypatch).send(notifications.Channel.sms, PHONE, MESSAGE)
    assert result.retryable is True
    assert "secret-token" not in (result.error or "")


def test_twilio_without_sender_fails_clearly(monkeypatch):
    provider = twilio(lambda _: httpx.Response(201, json={}), monkeypatch, TWILIO_SMS_FROM="")
    assert provider.can_send(notifications.Channel.sms) is False
    result = provider.send(notifications.Channel.sms, PHONE, MESSAGE)
    assert result.error == "No sms sender is set up"


def test_twilio_mode_requires_credentials():
    with pytest.raises(ValueError, match="TWILIO_ACCOUNT_SID"):
        Settings(
            DATABASE_URL="sqlite://",
            SECRET_KEY="x" * 40,
            NOTIFICATION_PROVIDER="twilio",
            TWILIO_ACCOUNT_SID="",
        )


def test_delivery_loop_helper_runs(client, auth, restaurant_id, table_id, db):
    alert_setup(db, client, auth, restaurant_id, table_id)
    delivery = db.scalar(select(AlertDelivery))
    delivery.created_at = utcnow()
    delivery.next_attempt_at = utcnow()
    db.commit()
    engine_loop._deliver_once()
    db.refresh(delivery)
    assert delivery.status in {"logged", "skipped"}
