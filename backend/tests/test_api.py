from datetime import timedelta

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.models import Alert, AlertStatus, DiningTable, Restaurant, TableSession
from app.models.base import utcnow
from app.services import engine_loop, table_engine
from tests.conftest import register_and_login


def base(restaurant_id: int) -> str:
    return f"/api/v1/restaurants/{restaurant_id}"


def act(client, auth, restaurant_id, table_id, action, **extra):
    return client.post(
        f"{base(restaurant_id)}/tables/{table_id}/actions",
        json={"action": action, **extra},
        headers=auth,
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_endpoints_require_login(client):
    assert client.get("/api/v1/restaurants").status_code == 401


def test_other_users_restaurant_is_invisible(client, auth, restaurant_id, table_id):
    other = register_and_login(client, "other@example.com")
    url = base(restaurant_id)
    assert client.get("/api/v1/restaurants", headers=other).json() == []
    assert client.get(url, headers=other).status_code == 404
    assert client.get(f"{url}/floor", headers=other).status_code == 404
    assert client.get(f"{url}/analytics", headers=other).status_code == 404
    assert client.delete(url, headers=other).status_code == 404
    assert act(client, other, restaurant_id, table_id, "seat").status_code == 404


def test_table_from_another_restaurant_cannot_be_used(client, auth, restaurant_id, table_id):
    second = client.post("/api/v1/restaurants", json={"name": "Second"}, headers=auth).json()["id"]
    assert act(client, auth, second, table_id, "seat").status_code == 404


def test_restaurant_settings_validate(client, auth, restaurant_id):
    url = base(restaurant_id)
    ok = client.patch(url, json={"waiter_alert_seconds": 600, "name": "New"}, headers=auth)
    assert ok.json()["waiter_alert_seconds"] == 600
    assert ok.json()["name"] == "New"
    assert client.patch(url, json={"timezone": "Mars/Base"}, headers=auth).status_code == 422
    assert client.patch(url, json={"covers_per_waiter": 0}, headers=auth).status_code == 422
    bad = client.post(
        "/api/v1/restaurants", json={"name": "X", "timezone": "No/Zone"}, headers=auth
    )
    assert bad.status_code == 422


def test_table_crud_and_label_uniqueness(client, auth, restaurant_id, table_id):
    url = f"{base(restaurant_id)}/tables"
    duplicate = client.post(url, json={"label": "T1"}, headers=auth)
    assert duplicate.status_code == 409

    moved = client.patch(f"{url}/{table_id}", json={"x": 55.5, "y": 20, "seats": 6}, headers=auth)
    assert moved.json()["x"] == 55.5
    assert moved.json()["seats"] == 6
    assert client.patch(f"{url}/{table_id}", json={"x": 101}, headers=auth).status_code == 422

    assert client.delete(f"{url}/{table_id}", headers=auth).status_code == 204
    assert client.get(url, headers=auth).json() == []
    assert client.post(url, json={"label": "T1"}, headers=auth).status_code == 201


def test_occupied_table_cannot_be_deleted(client, auth, restaurant_id, table_id):
    assert act(client, auth, restaurant_id, table_id, "seat").status_code == 200
    response = client.delete(f"{base(restaurant_id)}/tables/{table_id}", headers=auth)
    assert response.status_code == 409


def test_manual_flow_shows_on_floor(client, auth, restaurant_id, table_id):
    url = f"{base(restaurant_id)}/floor"
    assert act(client, auth, restaurant_id, table_id, "seat", party_size=3).status_code == 200
    table = client.get(url, headers=auth).json()["tables"][0]
    assert table["status"] == "occupied"
    assert table["party_size"] == 3
    assert table["seated_at"]
    assert table["first_served_at"] is None

    assert act(client, auth, restaurant_id, table_id, "served").status_code == 200
    assert client.get(url, headers=auth).json()["tables"][0]["first_served_at"]

    assert act(client, auth, restaurant_id, table_id, "vacate").status_code == 200
    assert client.get(url, headers=auth).json()["tables"][0]["status"] == "needs_cleaning"

    assert act(client, auth, restaurant_id, table_id, "cleaned").status_code == 200
    table = client.get(url, headers=auth).json()["tables"][0]
    assert table["status"] == "free"
    assert table["party_size"] is None

    assert act(client, auth, restaurant_id, table_id, "served").status_code == 409


def test_alert_is_listed_then_acknowledged(client, auth, restaurant_id, table_id, db):
    act(client, auth, restaurant_id, table_id, "seat")
    restaurant = db.get(Restaurant, restaurant_id)
    table_engine.evaluate_alerts(db, restaurant, utcnow() + timedelta(seconds=301))
    db.commit()

    floor = client.get(f"{base(restaurant_id)}/floor", headers=auth).json()
    assert floor["alerts"][0]["type"] == "waiter"
    assert floor["alerts"][0]["table_label"] == "T1"
    alert_id = floor["alerts"][0]["id"]

    response = client.post(f"{base(restaurant_id)}/alerts/{alert_id}/acknowledge", headers=auth)
    assert response.json()["status"] == "acknowledged"
    assert response.json()["acknowledged_at"]

    # Acknowledged means someone is on it. It stays on the board until the guests are served.
    assert len(client.get(f"{base(restaurant_id)}/floor", headers=auth).json()["alerts"]) == 1
    act(client, auth, restaurant_id, table_id, "served")
    assert client.get(f"{base(restaurant_id)}/floor", headers=auth).json()["alerts"] == []

    history = client.get(f"{base(restaurant_id)}/alerts", headers=auth).json()
    assert history[0]["status"] == AlertStatus.resolved.value
    missing = client.post(f"{base(restaurant_id)}/alerts/99999/acknowledge", headers=auth)
    assert missing.status_code == 404


def test_waitlist_suggests_distinct_big_enough_tables(client, auth, restaurant_id, table_id):
    url = base(restaurant_id)
    big = client.post(f"{url}/tables", json={"label": "T2", "seats": 8}, headers=auth).json()
    first = client.post(f"{url}/waitlist", json={"name": "Asha", "party_size": 6}, headers=auth)
    assert first.status_code == 201
    assert first.json()["suggested_table_id"] == big["id"]
    assert first.json()["estimated_wait_minutes"] == 0

    client.post(f"{url}/waitlist", json={"name": "Ben", "party_size": 2}, headers=auth)
    client.post(f"{url}/waitlist", json={"name": "Chen", "party_size": 2}, headers=auth)
    waitlist = client.get(f"{url}/waitlist", headers=auth).json()
    assert waitlist[1]["suggested_table_id"] == table_id
    assert waitlist[2]["suggested_table_id"] is None


def test_waitlist_seat_and_leave(client, auth, restaurant_id, table_id):
    url = f"{base(restaurant_id)}/waitlist"
    big = client.post(url, json={"name": "Big", "party_size": 9}, headers=auth).json()
    small = client.post(url, json={"name": "Small", "party_size": 2}, headers=auth).json()

    too_small = client.post(f"{url}/{big['id']}/seat", json={"table_id": table_id}, headers=auth)
    assert too_small.status_code == 409

    seated = client.post(f"{url}/{small['id']}/seat", json={"table_id": table_id}, headers=auth)
    assert seated.status_code == 204
    floor = client.get(f"{base(restaurant_id)}/floor", headers=auth).json()
    assert floor["tables"][0]["party_size"] == 2

    again = client.post(f"{url}/{small['id']}/seat", json={"table_id": table_id}, headers=auth)
    assert again.status_code == 409

    assert client.post(f"{url}/{big['id']}/leave", headers=auth).status_code == 204
    assert client.get(url, headers=auth).json() == []
    assert client.post(f"{url}/99999/leave", headers=auth).status_code == 404


def test_prediction_uses_default_then_history(client, auth, restaurant_id, table_id, db):
    now = utcnow()
    act(client, auth, restaurant_id, table_id, "seat")
    floor = client.get(f"{base(restaurant_id)}/floor", headers=auth).json()
    prediction = floor["predictions"][0]
    assert prediction["based_on_history"] is False
    assert 46 <= prediction["minutes_until_free"] <= 49  # 45 minute default plus cleaning

    for days in range(1, 7):
        seated = now - timedelta(days=days)
        db.add(
            TableSession(
                restaurant_id=restaurant_id,
                table_id=table_id,
                party_size=2,
                seated_at=seated,
                vacated_at=seated + timedelta(minutes=20),
                cleaned_at=seated + timedelta(minutes=21),
            )
        )
    db.commit()
    prediction = client.get(f"{base(restaurant_id)}/floor", headers=auth).json()["predictions"][0]
    assert prediction["based_on_history"] is True
    assert prediction["minutes_until_free"] == 21


def test_api_key_is_shown_once_and_stored_hashed(client, auth, restaurant_id, db):
    key = client.post(f"{base(restaurant_id)}/api-key", headers=auth).json()["api_key"]
    assert key.startswith("dos_")
    stored = db.get(Restaurant, restaurant_id).api_key_hash
    assert stored and stored != key
    assert client.get(base(restaurant_id), headers=auth).json()["has_api_key"] is True


def test_ingest_requires_valid_key(client):
    body = {"observations": [{"table_id": 1, "guest_count": 1}]}
    assert client.post("/api/v1/ingest/observations", json=body).status_code == 422
    response = client.post("/api/v1/ingest/observations", json=body, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_ingest_drives_the_table_and_rejects_other_restaurants_tables(
    client, auth, restaurant_id, table_id, db
):
    client.patch(base(restaurant_id), json={"seat_confirm_seconds": 0}, headers=auth)
    key = client.post(f"{base(restaurant_id)}/api-key", headers=auth).json()["api_key"]
    headers = {"X-API-Key": key}
    body = {"observations": [{"table_id": table_id, "guest_count": 2}]}

    response = client.post("/api/v1/ingest/observations", json=body, headers=headers)
    assert response.json() == {"accepted": 1, "changed": 1}
    table = client.get(f"{base(restaurant_id)}/floor", headers=auth).json()["tables"][0]
    assert table["status"] == "occupied"
    assert table["session_source"] == "camera"

    other = register_and_login(client, "other@example.com")
    theirs = client.post("/api/v1/restaurants", json={"name": "Theirs"}, headers=other).json()["id"]
    their_table = client.post(f"{base(theirs)}/tables", json={"label": "A"}, headers=other).json()[
        "id"
    ]
    body = {"observations": [{"table_id": their_table, "guest_count": 2}]}
    assert client.post("/api/v1/ingest/observations", json=body, headers=headers).status_code == 404
    assert db.get(DiningTable, their_table).status == "free"


def test_simulator_refuses_real_restaurants(client, auth, restaurant_id):
    response = client.post(f"{base(restaurant_id)}/simulator", json={"enabled": True}, headers=auth)
    assert response.status_code == 409


def test_engine_tick_ignores_simulator_flag_on_real_restaurant(
    client, auth, restaurant_id, table_id, db
):
    restaurant = db.get(Restaurant, restaurant_id)
    restaurant.simulator_enabled = True
    db.commit()
    for second in range(0, 300, 5):
        engine_loop.tick(db, utcnow() + timedelta(seconds=second))
    assert db.scalars(select(TableSession)).all() == []


def test_demo_is_flagged_idempotent_and_simulated(client, auth, db):
    response = client.post("/api/v1/restaurants/demo", json={"timezone": "UTC"}, headers=auth)
    assert response.status_code == 201
    demo = response.json()
    assert demo["is_demo"] is True
    assert demo["simulator_enabled"] is True
    again = client.post("/api/v1/restaurants/demo", json={"timezone": "UTC"}, headers=auth)
    assert again.json()["id"] == demo["id"]

    analytics = client.get(f"{base(demo['id'])}/analytics?days=28", headers=auth).json()
    assert analytics["is_sample_data"] is True
    assert analytics["parties"] > 100
    assert analytics["waiter_alerts"] > 0
    assert analytics["peak_hour"] in {12, 13, 14, 19, 20, 21, 22, 23}

    # Run the simulated floor for ten minutes and check every state and alert type shows up.
    start = utcnow()
    seen = set()
    for second in range(0, 600, 2):
        engine_loop.tick(db, start + timedelta(seconds=second))
        statuses = db.scalars(
            select(DiningTable.status).where(DiningTable.restaurant_id == demo["id"])
        ).all()
        seen.update(statuses)
    assert seen == {"free", "occupied", "needs_cleaning"}
    live_alerts = db.scalars(
        select(Alert.type).where(Alert.restaurant_id == demo["id"], Alert.created_at >= start)
    ).all()
    assert {"waiter", "cleaning"} <= set(live_alerts)

    off = client.post(f"{base(demo['id'])}/simulator", json={"enabled": False}, headers=auth)
    assert off.json()["simulator_enabled"] is False


def test_analytics_uses_restaurant_timezone_and_suggests_waiters(client, auth, db):
    restaurant = client.post(
        "/api/v1/restaurants", json={"name": "Delhi", "timezone": "Asia/Kolkata"}, headers=auth
    ).json()
    table = client.post(
        f"{base(restaurant['id'])}/tables", json={"label": "T1", "seats": 50}, headers=auth
    ).json()
    now = utcnow()
    seated = (now - timedelta(days=2)).replace(hour=14, minute=45, second=0, microsecond=0)
    db.add(
        TableSession(
            restaurant_id=restaurant["id"],
            table_id=table["id"],
            party_size=45,
            seated_at=seated,  # 14:45 UTC is 20:15 in India
            first_served_at=seated + timedelta(minutes=2),
            vacated_at=seated + timedelta(minutes=30),
            cleaned_at=seated + timedelta(minutes=33),
        )
    )
    db.commit()

    data = client.get(f"{base(restaurant['id'])}/analytics?days=7", headers=auth).json()
    assert data["parties"] == 1
    assert data["covers"] == 45
    assert data["avg_turn_minutes"] == 30
    assert data["avg_wait_for_service_seconds"] == 120
    assert data["avg_cleaning_seconds"] == 180
    assert data["peak_hour"] == 20
    assert data["is_sample_data"] is False
    # 45 covers across one or two matching weekdays, with 20 covers per waiter.
    assert data["heatmap"][0]["suggested_waiters"] in {2, 3}


def test_demo_peak_hours_are_local_mealtimes(client, auth):
    demo = client.post(
        "/api/v1/restaurants/demo", json={"timezone": "Asia/Kolkata"}, headers=auth
    ).json()
    data = client.get(f"{base(demo['id'])}/analytics?days=28", headers=auth).json()
    assert 19 <= data["peak_hour"] <= 23


def test_live_simulation_does_not_distort_demo_analytics(client, auth, db):
    demo = client.post("/api/v1/restaurants/demo", json={"timezone": "UTC"}, headers=auth).json()
    url = f"{base(demo['id'])}/analytics?days=7"
    before = client.get(url, headers=auth).json()
    prediction_before = client.get(f"{base(demo['id'])}/floor", headers=auth).json()["predictions"]

    start = utcnow()
    for second in range(0, 600, 2):
        engine_loop.tick(db, start + timedelta(seconds=second))
    live = db.scalars(select(TableSession).where(TableSession.source == "simulated")).all()
    assert len(live) > 10

    after = client.get(url, headers=auth).json()
    for field in ("parties", "covers", "avg_turn_minutes", "peak_hour", "waiter_alerts"):
        assert after[field] == before[field]
    # Turn estimates must stay in real minutes, not the seconds a sped-up table lasts.
    floor = client.get(f"{base(demo['id'])}/floor", headers=auth).json()
    assert prediction_before[0]["based_on_history"] is True
    occupied = [p for p in floor["predictions"] if p["status"] == "occupied"]
    assert occupied
    assert all(p["minutes_until_free"] > 15 for p in occupied)


def test_analytics_with_no_data_and_bad_range(client, auth, restaurant_id):
    url = f"{base(restaurant_id)}/analytics"
    data = client.get(url, headers=auth).json()
    assert data["parties"] == 0
    assert data["avg_turn_minutes"] is None
    assert data["peak_hour"] is None
    assert client.get(f"{url}?days=0", headers=auth).status_code == 422


def test_delete_restaurant_removes_everything(client, auth, restaurant_id, table_id, db):
    act(client, auth, restaurant_id, table_id, "seat")
    client.post(
        f"{base(restaurant_id)}/waitlist", json={"name": "A", "party_size": 2}, headers=auth
    )
    assert client.delete(base(restaurant_id), headers=auth).status_code == 204
    assert client.get(base(restaurant_id), headers=auth).status_code == 404
    assert db.scalars(select(TableSession)).all() == []


def test_websocket_rejects_bad_token_and_wrong_owner(client, auth, restaurant_id):
    url = f"/api/v1/ws/restaurants/{restaurant_id}"
    with client.websocket_connect(url) as socket:
        socket.send_json({"token": "nonsense"})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4401

    other = register_and_login(client, "other@example.com")["Authorization"].split()[1]
    with client.websocket_connect(url) as socket:
        socket.send_json({"token": other})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_websocket_receives_live_update(client, auth, restaurant_id, table_id):
    token = auth["Authorization"].split()[1]
    with client.websocket_connect(f"/api/v1/ws/restaurants/{restaurant_id}") as socket:
        socket.send_json({"token": token})
        assert socket.receive_json() == {"type": "ready"}
        act(client, auth, restaurant_id, table_id, "seat")
        assert socket.receive_json() == {"type": "floor_changed"}
