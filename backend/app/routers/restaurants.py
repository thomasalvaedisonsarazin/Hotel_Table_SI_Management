from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user, new_api_key, sha256
from app.database import get_db
from app.exceptions import ConflictError, NotFoundError
from app.models import (
    Alert,
    AlertStatus,
    DiningTable,
    Restaurant,
    TableSession,
    TableStatus,
    User,
    WaitlistEntry,
    WaitlistStatus,
)
from app.models.base import utcnow
from app.schemas.restaurant import (
    AlertResponse,
    AnalyticsResponse,
    ApiKeyResponse,
    DemoCreate,
    FloorResponse,
    FloorTable,
    RestaurantCreate,
    RestaurantResponse,
    RestaurantUpdate,
    SimulatorToggle,
    TableAction,
    TableCreate,
    TablePrediction,
    TableResponse,
    TableUpdate,
    WaitlistCreate,
    WaitlistResponse,
    WaitlistSeat,
)
from app.services import insights, table_engine
from app.services.demo import create_demo_restaurant
from app.services.hub import publish_floor_changed

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def get_owned_restaurant(
    restaurant_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Restaurant:
    restaurant = db.get(Restaurant, restaurant_id)
    # Same response for "missing" and "someone else's", so ids can't be probed.
    if restaurant is None or restaurant.owner_id != user.id:
        raise NotFoundError("Restaurant")
    return restaurant


def _restaurant_response(restaurant: Restaurant) -> RestaurantResponse:
    response = RestaurantResponse.model_validate(restaurant)
    response.has_api_key = restaurant.api_key_hash is not None
    return response


def _active_tables(db: Session, restaurant_id: int) -> list[DiningTable]:
    return list(
        db.scalars(
            select(DiningTable)
            .where(DiningTable.restaurant_id == restaurant_id, DiningTable.is_deleted.is_(False))
            .order_by(DiningTable.id)
        ).all()
    )


def _get_table(db: Session, restaurant_id: int, table_id: int, lock: bool = False) -> DiningTable:
    query = select(DiningTable).where(
        DiningTable.id == table_id,
        DiningTable.restaurant_id == restaurant_id,
        DiningTable.is_deleted.is_(False),
    )
    table = db.scalar(query.with_for_update() if lock else query)
    if table is None:
        raise NotFoundError("Table")
    return table


def _ensure_label_free(
    db: Session, restaurant_id: int, label: str, exclude_id: int | None = None
) -> None:
    query = select(DiningTable.id).where(
        DiningTable.restaurant_id == restaurant_id,
        DiningTable.label == label,
        DiningTable.is_deleted.is_(False),
    )
    if exclude_id is not None:
        query = query.where(DiningTable.id != exclude_id)
    if db.scalar(query):
        raise ConflictError(f"A table labelled {label} already exists")


def _alert_responses(rows: list[tuple[Alert, str]]) -> list[AlertResponse]:
    responses = []
    for alert, label in rows:
        response = AlertResponse.model_validate(alert)
        response.table_label = label
        responses.append(response)
    return responses


def _waitlist_responses(
    entries: list[WaitlistEntry], predictions: list[TablePrediction]
) -> list[WaitlistResponse]:
    """Match parties to tables in queue order, so two parties aren't promised the same table."""
    remaining = list(predictions)
    responses = []
    for entry in entries:
        match = next((p for p in remaining if p.seats >= entry.party_size), None)
        if match:
            remaining.remove(match)
        responses.append(
            WaitlistResponse(
                id=entry.id,
                name=entry.name,
                party_size=entry.party_size,
                status=entry.status,
                joined_at=entry.joined_at,
                seated_at=entry.seated_at,
                table_id=entry.table_id,
                estimated_wait_minutes=match.minutes_until_free if match else None,
                suggested_table_id=match.table_id if match else None,
                suggested_table_label=match.label if match else None,
            )
        )
    return responses


def _waiting_entries(db: Session, restaurant_id: int) -> list[WaitlistEntry]:
    return list(
        db.scalars(
            select(WaitlistEntry)
            .where(
                WaitlistEntry.restaurant_id == restaurant_id,
                WaitlistEntry.status == WaitlistStatus.waiting.value,
            )
            .order_by(WaitlistEntry.joined_at, WaitlistEntry.id)
        ).all()
    )


def _build_floor(db: Session, restaurant: Restaurant) -> FloorResponse:
    now = utcnow()
    tables = _active_tables(db, restaurant.id)
    sessions = db.scalars(
        select(TableSession).where(
            TableSession.restaurant_id == restaurant.id, TableSession.cleaned_at.is_(None)
        )
    ).all()
    session_by_table = {s.table_id: s for s in sessions}

    floor_tables = []
    for table in tables:
        item = FloorTable.model_validate(table)
        session = session_by_table.get(table.id)
        if session and table.status != TableStatus.free.value:
            item.party_size = session.party_size
            item.seated_at = session.seated_at
            item.first_served_at = session.first_served_at
            item.vacated_at = session.vacated_at
            item.session_source = session.source
        floor_tables.append(item)

    alert_rows = db.execute(
        select(Alert, DiningTable.label)
        .join(DiningTable, DiningTable.id == Alert.table_id)
        .where(
            Alert.restaurant_id == restaurant.id,
            Alert.status != AlertStatus.resolved.value,
        )
        .order_by(Alert.created_at.desc())
    ).all()

    seated_at = {s.table_id: s.seated_at for s in sessions if s.vacated_at is None}
    predictions = insights.predict_free_tables(db, restaurant, tables, seated_at, now)
    return FloorResponse(
        server_time=now,
        restaurant=_restaurant_response(restaurant),
        tables=floor_tables,
        alerts=_alert_responses([(a, label) for a, label in alert_rows]),
        waitlist=_waitlist_responses(_waiting_entries(db, restaurant.id), predictions),
        predictions=predictions,
    )


@router.get("", response_model=list[RestaurantResponse])
def list_restaurants(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[RestaurantResponse]:
    rows = db.scalars(
        select(Restaurant).where(Restaurant.owner_id == user.id).order_by(Restaurant.id)
    ).all()
    return [_restaurant_response(r) for r in rows]


@router.post("", status_code=201, response_model=RestaurantResponse)
def create_restaurant(
    req: RestaurantCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantResponse:
    restaurant = Restaurant(owner_id=user.id, name=req.name, timezone=req.timezone)
    db.add(restaurant)
    db.commit()
    return _restaurant_response(restaurant)


@router.post("/demo", status_code=201, response_model=RestaurantResponse)
def create_demo(
    req: DemoCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantResponse:
    return _restaurant_response(create_demo_restaurant(db, user, req.timezone, utcnow()))


@router.get("/{restaurant_id}", response_model=RestaurantResponse)
def get_restaurant(restaurant: Restaurant = Depends(get_owned_restaurant)) -> RestaurantResponse:
    return _restaurant_response(restaurant)


@router.patch("/{restaurant_id}", response_model=RestaurantResponse)
def update_restaurant(
    req: RestaurantUpdate,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> RestaurantResponse:
    for field, value in req.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(restaurant, field, value)
    db.commit()
    publish_floor_changed(restaurant.id)
    return _restaurant_response(restaurant)


@router.delete("/{restaurant_id}", status_code=204)
def delete_restaurant(
    restaurant: Restaurant = Depends(get_owned_restaurant), db: Session = Depends(get_db)
) -> None:
    for model in (Alert, WaitlistEntry, TableSession, DiningTable):
        for row in db.scalars(select(model).where(model.restaurant_id == restaurant.id)).all():
            db.delete(row)
        db.flush()
    db.delete(restaurant)
    db.commit()


@router.post("/{restaurant_id}/api-key", response_model=ApiKeyResponse)
def rotate_api_key(
    restaurant: Restaurant = Depends(get_owned_restaurant), db: Session = Depends(get_db)
) -> ApiKeyResponse:
    """Create a new camera key. Only its hash is stored, so this is the one time it can be read."""
    key = new_api_key()
    restaurant.api_key_hash = sha256(key)
    db.commit()
    return ApiKeyResponse(api_key=key)


@router.post("/{restaurant_id}/simulator", response_model=RestaurantResponse)
def toggle_simulator(
    req: SimulatorToggle,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> RestaurantResponse:
    if not restaurant.is_demo:
        raise ConflictError("The simulator only runs on demo restaurants")
    restaurant.simulator_enabled = req.enabled
    db.commit()
    publish_floor_changed(restaurant.id)
    return _restaurant_response(restaurant)


@router.get("/{restaurant_id}/floor", response_model=FloorResponse)
def get_floor(
    restaurant: Restaurant = Depends(get_owned_restaurant), db: Session = Depends(get_db)
) -> FloorResponse:
    return _build_floor(db, restaurant)


@router.get("/{restaurant_id}/tables", response_model=list[TableResponse])
def list_tables(
    restaurant: Restaurant = Depends(get_owned_restaurant), db: Session = Depends(get_db)
) -> list[DiningTable]:
    return _active_tables(db, restaurant.id)


@router.post("/{restaurant_id}/tables", status_code=201, response_model=TableResponse)
def create_table(
    req: TableCreate,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> DiningTable:
    _ensure_label_free(db, restaurant.id, req.label)
    table = DiningTable(restaurant_id=restaurant.id, **req.model_dump())
    db.add(table)
    db.commit()
    publish_floor_changed(restaurant.id)
    return table


@router.patch("/{restaurant_id}/tables/{table_id}", response_model=TableResponse)
def update_table(
    table_id: int,
    req: TableUpdate,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> DiningTable:
    table = _get_table(db, restaurant.id, table_id)
    if req.label is not None:
        _ensure_label_free(db, restaurant.id, req.label, exclude_id=table.id)
    for field, value in req.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(table, field, value)
    db.commit()
    publish_floor_changed(restaurant.id)
    return table


@router.delete("/{restaurant_id}/tables/{table_id}", status_code=204)
def delete_table(
    table_id: int,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> None:
    table = _get_table(db, restaurant.id, table_id, lock=True)
    if table.status != TableStatus.free.value:
        raise ConflictError("Only a free table can be removed")
    # Soft delete keeps this table's past sessions in the analytics.
    table.is_deleted = True
    db.commit()
    publish_floor_changed(restaurant.id)


@router.post("/{restaurant_id}/tables/{table_id}/actions", response_model=TableResponse)
def table_action(
    table_id: int,
    req: TableAction,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> DiningTable:
    table = _get_table(db, restaurant.id, table_id, lock=True)
    now = utcnow()
    if req.action == "seat":
        table_engine.seat_table(db, table, req.party_size, now, now, "manual")
    elif req.action == "served":
        table_engine.serve_table(db, table, now)
    elif req.action == "vacate":
        table_engine.vacate_table(db, table, now, now)
    else:
        table_engine.clean_table(db, table, now)
    db.commit()
    publish_floor_changed(restaurant.id)
    return table


@router.get("/{restaurant_id}/alerts", response_model=list[AlertResponse])
def list_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> list[AlertResponse]:
    rows = db.execute(
        select(Alert, DiningTable.label)
        .join(DiningTable, DiningTable.id == Alert.table_id)
        .where(Alert.restaurant_id == restaurant.id)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(limit)
    ).all()
    return _alert_responses([(a, label) for a, label in rows])


@router.post("/{restaurant_id}/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: int,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> AlertResponse:
    row = db.execute(
        select(Alert, DiningTable.label)
        .join(DiningTable, DiningTable.id == Alert.table_id)
        .where(Alert.id == alert_id, Alert.restaurant_id == restaurant.id)
    ).first()
    if row is None:
        raise NotFoundError("Alert")
    alert, label = row
    if alert.status == AlertStatus.open.value:
        alert.status = AlertStatus.acknowledged.value
        alert.acknowledged_at = utcnow()
        db.commit()
        publish_floor_changed(restaurant.id)
    return _alert_responses([(alert, label)])[0]


@router.get("/{restaurant_id}/waitlist", response_model=list[WaitlistResponse])
def list_waitlist(
    restaurant: Restaurant = Depends(get_owned_restaurant), db: Session = Depends(get_db)
) -> list[WaitlistResponse]:
    return _build_floor(db, restaurant).waitlist


@router.post("/{restaurant_id}/waitlist", status_code=201, response_model=WaitlistResponse)
def add_to_waitlist(
    req: WaitlistCreate,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> WaitlistResponse:
    entry = WaitlistEntry(
        restaurant_id=restaurant.id,
        name=req.name,
        party_size=req.party_size,
        joined_at=utcnow(),
    )
    db.add(entry)
    db.commit()
    publish_floor_changed(restaurant.id)
    return next(w for w in _build_floor(db, restaurant).waitlist if w.id == entry.id)


def _get_waiting_entry(db: Session, restaurant_id: int, entry_id: int) -> WaitlistEntry:
    entry = db.scalar(
        select(WaitlistEntry).where(
            WaitlistEntry.id == entry_id, WaitlistEntry.restaurant_id == restaurant_id
        )
    )
    if entry is None:
        raise NotFoundError("Waitlist entry")
    if entry.status != WaitlistStatus.waiting.value:
        raise ConflictError("This party is no longer waiting")
    return entry


@router.post("/{restaurant_id}/waitlist/{entry_id}/seat", status_code=204)
def seat_from_waitlist(
    entry_id: int,
    req: WaitlistSeat,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> None:
    entry = _get_waiting_entry(db, restaurant.id, entry_id)
    table = _get_table(db, restaurant.id, req.table_id, lock=True)
    if table.seats < entry.party_size:
        raise ConflictError(f"Table {table.label} seats {table.seats}, party is {entry.party_size}")
    now = utcnow()
    table_engine.seat_table(db, table, entry.party_size, now, now, "manual")
    entry.status = WaitlistStatus.seated.value
    entry.seated_at = now
    entry.table_id = table.id
    db.commit()
    publish_floor_changed(restaurant.id)


@router.post("/{restaurant_id}/waitlist/{entry_id}/leave", status_code=204)
def leave_waitlist(
    entry_id: int,
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> None:
    entry = _get_waiting_entry(db, restaurant.id, entry_id)
    entry.status = WaitlistStatus.left.value
    db.commit()
    publish_floor_changed(restaurant.id)


@router.get("/{restaurant_id}/analytics", response_model=AnalyticsResponse)
def get_analytics(
    days: int = Query(default=7, ge=1, le=90),
    restaurant: Restaurant = Depends(get_owned_restaurant),
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    return insights.build_analytics(db, restaurant, days, utcnow())
