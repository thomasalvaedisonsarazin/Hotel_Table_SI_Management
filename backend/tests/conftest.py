import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

# Set before the app is imported, because settings and the engine are created on import.
_tmp = Path(tempfile.mkdtemp(prefix="tablesense-tests-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["ENGINE_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth.security import auth_rate_limit  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DiningTable, Restaurant, User  # noqa: E402
from app.services import engine_loop  # noqa: E402

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)  # A Monday


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    auth_rate_limit.reset()
    engine_loop._scripts.clear()
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse"}
    )
    assert response.status_code == 201
    response = client.post(
        "/api/v1/auth/login", data={"username": email, "password": "correct-horse"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register_and_login(client)


@pytest.fixture
def restaurant_id(client: TestClient, auth: dict[str, str]) -> int:
    response = client.post("/api/v1/restaurants", json={"name": "Cafe"}, headers=auth)
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def table_id(client: TestClient, auth: dict[str, str], restaurant_id: int) -> int:
    response = client.post(
        f"/api/v1/restaurants/{restaurant_id}/tables",
        json={"label": "T1", "seats": 4},
        headers=auth,
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def engine_setup(db: Session) -> tuple[Restaurant, DiningTable]:
    """A restaurant with default thresholds and one free table, for direct engine tests."""
    user = User(email="engine@example.com", hashed_password="x")
    db.add(user)
    db.flush()
    restaurant = Restaurant(
        owner_id=user.id,
        name="Engine",
        timezone="UTC",
        is_demo=False,
        simulator_enabled=False,
        waiter_alert_seconds=300,
        cleaning_alert_seconds=120,
        seat_confirm_seconds=30,
        vacate_confirm_seconds=90,
        service_confirm_seconds=10,
        clean_confirm_seconds=30,
        default_turn_minutes=45,
        covers_per_waiter=20,
    )
    db.add(restaurant)
    db.flush()
    table = DiningTable(restaurant_id=restaurant.id, label="T1", seats=4, x=10, y=10, status="free")
    db.add(table)
    db.commit()
    return restaurant, table
