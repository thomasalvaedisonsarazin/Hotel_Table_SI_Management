"""Creates a clearly flagged demo restaurant with sample history and fast thresholds."""

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, AlertStatus, AlertType, DiningTable, Restaurant, TableSession, User

_LAYOUT = [
    ("T1", 2, 14, 18),
    ("T2", 2, 38, 18),
    ("T3", 4, 62, 18),
    ("T4", 4, 86, 18),
    ("T5", 4, 14, 50),
    ("T6", 6, 38, 50),
    ("T7", 4, 62, 50),
    ("T8", 2, 86, 50),
    ("T9", 2, 14, 82),
    ("T10", 4, 38, 82),
    ("T11", 8, 62, 82),
    ("T12", 2, 86, 82),
]

_HISTORY_DAYS = 28


def _hourly_parties(weekday: int, hour: int) -> float:
    base = {12: 3.0, 13: 4.0, 14: 2.0, 19: 3.0, 20: 5.0, 21: 4.0, 22: 1.5}.get(hour, 0.5)
    return base * (1.5 if weekday >= 4 else 1.0)


def _resolved_alert(
    session: TableSession, kind: AlertType, after_seconds: float, resolved_seconds: float
) -> Alert:
    start = session.seated_at if kind is AlertType.waiter else session.vacated_at
    assert start is not None  # noqa: S101
    return Alert(
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        session_id=session.id,
        type=kind.value,
        status=AlertStatus.resolved.value,
        created_at=start + timedelta(seconds=after_seconds),
        resolved_at=start + timedelta(seconds=resolved_seconds),
    )


def _add_history(
    db: Session, restaurant: Restaurant, tables: list[DiningTable], now: datetime
) -> None:
    rng = random.Random(restaurant.id)
    tz = ZoneInfo(restaurant.timezone)
    for days_ago in range(1, _HISTORY_DAYS + 1):
        # Peaks are local mealtimes, so build the history in the restaurant's own timezone.
        day = now.astimezone(tz) - timedelta(days=days_ago)
        for hour in range(11, 23):
            parties = rng.gauss(_hourly_parties(day.weekday(), hour), 0.6)
            for _ in range(max(0, round(parties))):
                table = rng.choice(tables)
                seated = day.replace(hour=hour, minute=rng.randint(0, 59), second=0, microsecond=0)
                service_wait = rng.uniform(60, 420)
                vacated = seated + timedelta(minutes=rng.uniform(30, 75))
                cleaning = rng.uniform(60, 300)
                session = TableSession(
                    restaurant_id=restaurant.id,
                    table_id=table.id,
                    party_size=rng.randint(1, table.seats),
                    source="sample",
                    seated_at=seated,
                    first_served_at=seated + timedelta(seconds=service_wait),
                    vacated_at=vacated,
                    cleaned_at=vacated + timedelta(seconds=cleaning),
                )
                db.add(session)
                db.flush()
                if service_wait >= 300:
                    db.add(_resolved_alert(session, AlertType.waiter, 300, service_wait))
                if cleaning >= 120:
                    db.add(_resolved_alert(session, AlertType.cleaning, 120, cleaning))


def create_demo_restaurant(db: Session, user: User, timezone: str, now: datetime) -> Restaurant:
    existing = db.scalar(
        select(Restaurant).where(Restaurant.owner_id == user.id, Restaurant.is_demo.is_(True))
    )
    if existing:
        return existing
    restaurant = Restaurant(
        owner_id=user.id,
        name="Demo Bistro",
        timezone=timezone,
        is_demo=True,
        simulator_enabled=True,
        # Shortened so a viewer sees the full table cycle within a couple of minutes.
        waiter_alert_seconds=45,
        cleaning_alert_seconds=20,
        seat_confirm_seconds=4,
        vacate_confirm_seconds=6,
        service_confirm_seconds=3,
        clean_confirm_seconds=5,
    )
    db.add(restaurant)
    db.flush()
    tables = [
        DiningTable(restaurant_id=restaurant.id, label=label, seats=seats, x=x, y=y)
        for label, seats, x, y in _LAYOUT
    ]
    db.add_all(tables)
    db.flush()
    _add_history(db, restaurant, tables, now)
    db.commit()
    return restaurant
