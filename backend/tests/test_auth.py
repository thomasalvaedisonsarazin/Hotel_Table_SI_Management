from datetime import timedelta

from sqlalchemy import select

from app.models import RefreshToken
from app.models.base import utcnow
from tests.conftest import register_and_login


def test_register_login_me(client):
    headers = register_and_login(client, "Mixed@Example.com")
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "mixed@example.com"
    assert "hashed_password" not in response.json()


def test_duplicate_email_conflicts(client):
    payload = {"email": "a@example.com", "password": "correct-horse"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_short_and_overlong_passwords_rejected(client):
    for password in ("short", "x" * 73):
        response = client.post(
            "/api/v1/auth/register", json={"email": "a@example.com", "password": password}
        )
        assert response.status_code == 422


def test_wrong_password_and_unknown_email_look_the_same(client):
    register_and_login(client)
    wrong = client.post(
        "/api/v1/auth/login", data={"username": "owner@example.com", "password": "nope-nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", data={"username": "ghost@example.com", "password": "nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_overlong_password_at_login_is_a_normal_failure(client):
    register_and_login(client)
    response = client.post(
        "/api/v1/auth/login", data={"username": "owner@example.com", "password": "x" * 100}
    )
    assert response.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401


def _login_tokens(client):
    register_and_login(client)
    return client.post(
        "/api/v1/auth/login", data={"username": "owner@example.com", "password": "correct-horse"}
    ).json()


def test_refresh_token_cannot_be_used_as_access_token(client):
    tokens = _login_tokens(client)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


def test_refresh_rotates_and_reuse_ends_all_sessions(client):
    tokens = _login_tokens(client)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    newer = first.json()["refresh_token"]
    assert newer != tokens["refresh_token"]

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": newer}).status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = _login_tokens(client)
    body = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/auth/logout", json=body).status_code == 204
    assert client.post("/api/v1/auth/refresh", json=body).status_code == 401


def test_expired_refresh_row_rejected(client, db):
    tokens = _login_tokens(client)
    for row in db.scalars(select(RefreshToken)).all():
        row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_login_is_rate_limited(client):
    responses = [
        client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "wrong"})
        for _ in range(11)
    ]
    assert responses[-1].status_code == 429
