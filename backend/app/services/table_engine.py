"""The table state machine. Camera observations, staff taps and the simulator all end up here."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import ConflictError
from app.models import (
    Alert,
    AlertStatus,
    AlertType,
    DiningTable,
    Restaurant,
    TableSession,
    TableStatus,
)

# A detector can miss people for a few frames. Gaps shorter than this don't reset a sighting.
PRESENCE_GAP = timedelta(seconds=10)


def open_session(db: Session, table: DiningTable) -> TableSession | None:
    return db.scalar(
        select(TableSession)
        .where(TableSession.table_id == table.id, TableSession.cleaned_at.is_(None))
        .order_by(TableSession.seated_at.desc(), TableSession.id.desc())
        .limit(1)
    )


def _set_status(table: DiningTable, status: TableStatus, now: datetime) -> None:
    table.status = status.value
    table.status_changed_at = now


def _resolve_alert(db: Session, session: TableSession, kind: AlertType, now: datetime) -> None:
    alert = db.scalar(
        select(Alert).where(
            Alert.session_id == session.id,
            Alert.type == kind.value,
            Alert.status != AlertStatus.resolved.value,
        )
    )
    if alert:
        alert.status = AlertStatus.resolved.value
        alert.resolved_at = now


def _mark_cleaned(db: Session, table: DiningTable, now: datetime) -> None:
    session = open_session(db, table)
    if session:
        session.cleaned_at = now
        _resolve_alert(db, session, AlertType.cleaning, now)


def seat_table(
    db: Session,
    table: DiningTable,
    party_size: int,
    seated_at: datetime,
    now: datetime,
    source: str,
) -> TableSession:
    if table.status == TableStatus.occupied.value:
        raise ConflictError("Table is already occupied")
    if table.status == TableStatus.needs_cleaning.value:
        _mark_cleaned(db, table, now)
    session = TableSession(
        restaurant_id=table.restaurant_id,
        table_id=table.id,
        party_size=party_size,
        source=source,
        seated_at=seated_at,
    )
    db.add(session)
    _set_status(table, TableStatus.occupied, now)
    table.guests_last_seen_at = now
    db.flush()
    return session


def serve_table(db: Session, table: DiningTable, now: datetime) -> None:
    session = open_session(db, table)
    if table.status != TableStatus.occupied.value or session is None:
        raise ConflictError("Only an occupied table can be marked as served")
    if session.first_served_at is None:
        session.first_served_at = now
    _resolve_alert(db, session, AlertType.waiter, now)


def vacate_table(db: Session, table: DiningTable, vacated_at: datetime, now: datetime) -> None:
    session = open_session(db, table)
    if table.status != TableStatus.occupied.value or session is None:
        raise ConflictError("Only an occupied table can be vacated")
    session.vacated_at = vacated_at
    _resolve_alert(db, session, AlertType.waiter, now)
    _set_status(table, TableStatus.needs_cleaning, now)
    table.guests_first_seen_at = None
    table.guests_last_seen_at = None


def clean_table(db: Session, table: DiningTable, now: datetime) -> None:
    if table.status != TableStatus.needs_cleaning.value:
        raise ConflictError("Only a table waiting for cleaning can be marked clean")
    _mark_cleaned(db, table, now)
    _set_status(table, TableStatus.free, now)
    table.staff_first_seen_at = None


def apply_observation(
    db: Session,
    restaurant: Restaurant,
    table: DiningTable,
    guest_count: int,
    staff_present: bool,
    now: datetime,
    source: str,
) -> bool:
    """Apply one observation of a table. Returns True if anything visible on the board changed."""
    before = table.status
    session_changed = False

    if guest_count > 0:
        last_seen = table.guests_last_seen_at
        if table.guests_first_seen_at is None or (
            last_seen is not None and now - last_seen > PRESENCE_GAP
        ):
            table.guests_first_seen_at = now
        table.guests_last_seen_at = now
    elif (
        table.status != TableStatus.occupied.value
        and table.guests_last_seen_at is not None
        and now - table.guests_last_seen_at > PRESENCE_GAP
    ):
        table.guests_first_seen_at = None
        table.guests_last_seen_at = None

    table.staff_first_seen_at = (table.staff_first_seen_at or now) if staff_present else None
    staff_for = (now - table.staff_first_seen_at) if table.staff_first_seen_at else None

    if table.status == TableStatus.occupied.value:
        session = open_session(db, table)
        if session and guest_count > session.party_size:
            session.party_size = guest_count
            session_changed = True
        if (
            session
            and session.first_served_at is None
            and staff_for is not None
            and staff_for >= timedelta(seconds=restaurant.service_confirm_seconds)
        ):
            serve_table(db, table, now)
            session_changed = True
        last_seen = table.guests_last_seen_at
        if (
            guest_count == 0
            and last_seen is not None
            and now - last_seen >= timedelta(seconds=restaurant.vacate_confirm_seconds)
        ):
            vacate_table(db, table, last_seen, now)
    else:
        first_seen = table.guests_first_seen_at
        if (
            guest_count > 0
            and first_seen is not None
            and now - first_seen >= timedelta(seconds=restaurant.seat_confirm_seconds)
        ):
            # The timer starts from when guests were first seen, not when we became sure.
            seat_table(db, table, guest_count, first_seen, now, source)
        elif (
            table.status == TableStatus.needs_cleaning.value
            and staff_for is not None
            and staff_for >= timedelta(seconds=restaurant.clean_confirm_seconds)
        ):
            clean_table(db, table, now)

    return table.status != before or session_changed


def evaluate_alerts(db: Session, restaurant: Restaurant, now: datetime) -> list[Alert]:
    """Raise any alerts now due. Each session gets at most one alert of each type."""
    rows = db.execute(
        select(DiningTable, TableSession)
        .join(TableSession, TableSession.table_id == DiningTable.id)
        .where(
            DiningTable.restaurant_id == restaurant.id,
            DiningTable.is_deleted.is_(False),
            DiningTable.status != TableStatus.free.value,
            TableSession.cleaned_at.is_(None),
        )
    ).all()

    created: list[Alert] = []
    for table, session in rows:
        kind: AlertType | None = None
        if (
            table.status == TableStatus.occupied.value
            and session.vacated_at is None
            and session.first_served_at is None
            and now - session.seated_at >= timedelta(seconds=restaurant.waiter_alert_seconds)
        ):
            kind = AlertType.waiter
        elif (
            table.status == TableStatus.needs_cleaning.value
            and session.vacated_at is not None
            and now - session.vacated_at >= timedelta(seconds=restaurant.cleaning_alert_seconds)
        ):
            kind = AlertType.cleaning
        if kind is None:
            continue
        exists = db.scalar(
            select(Alert.id).where(Alert.session_id == session.id, Alert.type == kind.value)
        )
        if exists:
            continue
        alert = Alert(
            restaurant_id=restaurant.id,
            table_id=table.id,
            session_id=session.id,
            type=kind.value,
            status=AlertStatus.open.value,
            created_at=now,
        )
        try:
            with db.begin_nested():
                db.add(alert)
        except IntegrityError:
            continue
        created.append(alert)
    return created
