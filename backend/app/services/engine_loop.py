"""Background loop: steps demo simulators, raises due alerts and tells browsers what changed."""

import asyncio
import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import DiningTable, Restaurant
from app.models.base import utcnow
from app.services import table_engine
from app.services.hub import hub, publish_floor_changed
from app.services.simulator import TableScript

logger = logging.getLogger(__name__)

_scripts: dict[int, TableScript] = {}


def _step_simulator(db: Session, restaurant: Restaurant, now: datetime) -> bool:
    tables = db.scalars(
        select(DiningTable).where(
            DiningTable.restaurant_id == restaurant.id, DiningTable.is_deleted.is_(False)
        )
    ).all()
    changed = False
    for table in tables:
        script = _scripts.get(table.id)
        if script is None:
            rng = random.Random(table.id)
            first_arrival = now + timedelta(seconds=rng.uniform(1, 25))
            script = TableScript(rng=rng, seats=table.seats, next_arrival=first_arrival)
            _scripts[table.id] = script
        guests, staff = script.observe(now)
        changed |= table_engine.apply_observation(
            db, restaurant, table, guests, staff, now, "simulated"
        )
    return changed


def tick(db: Session, now: datetime) -> None:
    restaurants = db.scalars(select(Restaurant)).all()
    for restaurant in restaurants:
        changed = False
        if restaurant.is_demo and restaurant.simulator_enabled:
            changed = _step_simulator(db, restaurant, now)
        alerts = table_engine.evaluate_alerts(db, restaurant, now)
        db.commit()
        for alert in alerts:
            hub.publish(
                restaurant.id,
                {
                    "type": "alert",
                    "alert_id": alert.id,
                    "table_id": alert.table_id,
                    "alert_type": alert.type,
                },
            )
        if changed or alerts:
            publish_floor_changed(restaurant.id)


def _tick_once() -> None:
    with SessionLocal() as db:
        tick(db, utcnow())


async def run_engine_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_tick_once)
        except Exception:
            logger.exception("Engine tick failed")
        await asyncio.sleep(settings.ENGINE_TICK_SECONDS)
