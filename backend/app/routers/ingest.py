"""The contract a camera worker uses to report what it sees. See the README for the format."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import sha256
from app.database import get_db
from app.exceptions import NotFoundError, UnauthorizedError
from app.models import DiningTable, Restaurant
from app.models.base import utcnow
from app.schemas.restaurant import IngestResult, ObservationBatch
from app.services import table_engine
from app.services.hub import publish_floor_changed

router = APIRouter(prefix="/ingest", tags=["ingest"])


def get_restaurant_from_key(x_api_key: str = Header(), db: Session = Depends(get_db)) -> Restaurant:
    restaurant = db.scalar(select(Restaurant).where(Restaurant.api_key_hash == sha256(x_api_key)))
    if restaurant is None:
        raise UnauthorizedError("Invalid API key")
    return restaurant


@router.post("/observations", response_model=IngestResult)
def ingest_observations(
    batch: ObservationBatch,
    restaurant: Restaurant = Depends(get_restaurant_from_key),
    db: Session = Depends(get_db),
) -> IngestResult:
    ids = {o.table_id for o in batch.observations}
    tables = {
        t.id: t
        for t in db.scalars(
            select(DiningTable)
            .where(
                DiningTable.id.in_(ids),
                DiningTable.restaurant_id == restaurant.id,
                DiningTable.is_deleted.is_(False),
            )
            .with_for_update()
        ).all()
    }
    if len(tables) != len(ids):
        raise NotFoundError("Table")

    now = utcnow()
    changed = sum(
        table_engine.apply_observation(
            db,
            restaurant,
            tables[o.table_id],
            o.guest_count,
            o.staff_present,
            now,
            "camera",
        )
        for o in batch.observations
    )
    db.commit()
    if changed:
        publish_floor_changed(restaurant.id)
    return IngestResult(accepted=len(batch.observations), changed=changed)
