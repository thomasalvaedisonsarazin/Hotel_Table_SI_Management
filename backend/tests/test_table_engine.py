from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import ConflictError
from app.models import Alert, DiningTable, Restaurant, TableSession
from app.services import table_engine as te
from tests.conftest import T0


def feed(
    db: Session,
    restaurant: Restaurant,
    table: DiningTable,
    guests: int,
    staff: bool,
    start_seconds: int,
    end_seconds: int,
    step: int = 2,
) -> None:
    """Send one observation every `step` seconds, as a camera worker would."""
    for second in range(start_seconds, end_seconds + 1, step):
        te.apply_observation(
            db, restaurant, table, guests, staff, T0 + timedelta(seconds=second), "camera"
        )
    db.commit()


def seat_by_camera(db: Session, restaurant: Restaurant, table: DiningTable) -> None:
    feed(db, restaurant, table, 3, False, 0, 30)
    assert table.status == "occupied"


def alerts(db: Session) -> list[Alert]:
    return list(db.scalars(select(Alert)).all())


def test_passer_by_does_not_occupy_table(db, engine_setup):
    restaurant, table = engine_setup
    feed(db, restaurant, table, 1, False, 0, 8)
    feed(db, restaurant, table, 0, False, 10, 60)
    assert table.status == "free"
    assert db.scalars(select(TableSession)).all() == []


def test_separate_passers_by_do_not_add_up_to_a_seating(db, engine_setup):
    restaurant, table = engine_setup
    feed(db, restaurant, table, 1, False, 0, 8)
    feed(db, restaurant, table, 0, False, 10, 40)
    feed(db, restaurant, table, 1, False, 42, 50)
    assert table.status == "free"


def test_guests_who_stay_occupy_table_with_timer_from_first_sighting(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    session = db.scalar(select(TableSession))
    assert session.seated_at == T0
    assert session.party_size == 3
    assert session.source == "camera"


def test_short_detection_dropout_does_not_reset_seating(db, engine_setup):
    restaurant, table = engine_setup
    feed(db, restaurant, table, 2, False, 0, 14)
    feed(db, restaurant, table, 0, False, 16, 18)  # missed for a few frames
    feed(db, restaurant, table, 2, False, 20, 30)
    assert table.status == "occupied"
    assert db.scalar(select(TableSession)).seated_at == T0


def test_dropout_does_not_end_a_session(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 0, False, 32, 80)  # under the 90 second confirm
    assert table.status == "occupied"
    feed(db, restaurant, table, 3, False, 82, 100)
    assert table.status == "occupied"
    assert len(db.scalars(select(TableSession)).all()) == 1


def test_guests_leaving_needs_cleaning_with_real_leaving_time(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 0, False, 32, 122)
    assert table.status == "needs_cleaning"
    assert db.scalar(select(TableSession)).vacated_at == T0 + timedelta(seconds=30)


def test_party_size_grows_when_more_guests_arrive(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 5, False, 32, 34)
    assert db.scalar(select(TableSession)).party_size == 5


def test_waiter_passing_by_is_not_service(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 3, True, 32, 36)  # 4 seconds, under the 10 second confirm
    feed(db, restaurant, table, 3, False, 38, 40)
    assert db.scalar(select(TableSession)).first_served_at is None


def test_waiter_alert_fires_at_threshold_once_and_resolves_on_service(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)

    assert te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=299)) == []
    fired = te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=300))
    db.commit()
    assert [a.type for a in fired] == ["waiter"]
    assert te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=400)) == []

    feed(db, restaurant, table, 3, True, 402, 412)
    assert alerts(db)[0].status == "resolved"
    assert alerts(db)[0].resolved_at == T0 + timedelta(seconds=412)


def test_no_waiter_alert_when_served_in_time(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 3, True, 32, 42)
    assert te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=1000)) == []


def test_waiter_alert_resolves_if_guests_leave_unserved(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=300))
    db.commit()
    feed(db, restaurant, table, 0, False, 302, 400)
    assert table.status == "needs_cleaning"
    waiter = next(a for a in alerts(db) if a.type == "waiter")
    assert waiter.status == "resolved"


def test_cleaning_alert_and_staff_visit_frees_table(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 0, False, 32, 122)
    vacated = db.scalar(select(TableSession)).vacated_at

    assert te.evaluate_alerts(db, restaurant, vacated + timedelta(seconds=119)) == []
    fired = te.evaluate_alerts(db, restaurant, vacated + timedelta(seconds=120))
    db.commit()
    assert [a.type for a in fired] == ["cleaning"]

    feed(db, restaurant, table, 0, True, 200, 230)
    assert table.status == "free"
    assert db.scalar(select(TableSession)).cleaned_at == T0 + timedelta(seconds=230)
    assert alerts(db)[0].status == "resolved"


def test_new_guests_on_dirty_table_start_new_session(db, engine_setup):
    restaurant, table = engine_setup
    seat_by_camera(db, restaurant, table)
    feed(db, restaurant, table, 0, False, 32, 122)
    te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=300))
    db.commit()
    feed(db, restaurant, table, 2, False, 302, 332)

    assert table.status == "occupied"
    sessions = db.scalars(select(TableSession).order_by(TableSession.id)).all()
    assert len(sessions) == 2
    assert sessions[0].cleaned_at is not None
    assert sessions[1].cleaned_at is None
    assert alerts(db)[0].status == "resolved"


def test_each_party_can_get_its_own_alert(db, engine_setup):
    restaurant, table = engine_setup
    for start in (0, 1000):
        te.seat_table(db, table, 2, T0 + timedelta(seconds=start), T0, "manual")
        te.evaluate_alerts(db, restaurant, T0 + timedelta(seconds=start + 300))
        te.vacate_table(db, table, T0 + timedelta(seconds=start + 400), T0)
        te.clean_table(db, table, T0 + timedelta(seconds=start + 410))
    db.commit()
    assert len(alerts(db)) == 2


@pytest.mark.parametrize(
    ("action", "status"),
    [
        (lambda db, t: te.serve_table(db, t, T0), "free"),
        (lambda db, t: te.vacate_table(db, t, T0, T0), "free"),
        (lambda db, t: te.clean_table(db, t, T0), "free"),
    ],
)
def test_invalid_manual_transitions_conflict(db, engine_setup, action, status):
    _, table = engine_setup
    with pytest.raises(ConflictError):
        action(db, table)
    assert table.status == status


def test_cannot_seat_an_occupied_table(db, engine_setup):
    _, table = engine_setup
    te.seat_table(db, table, 2, T0, T0, "manual")
    with pytest.raises(ConflictError):
        te.seat_table(db, table, 2, T0, T0, "manual")
