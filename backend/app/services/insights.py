"""Read-side calculations: next-free-table estimates and weekly analytics."""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, AlertType, DiningTable, Restaurant, TableSession, TableStatus
from app.schemas.restaurant import (
    AnalyticsResponse,
    HeatmapCell,
    HourlyPoint,
    TablePrediction,
)

# The live demo simulator runs on sped-up time, so its sessions would distort every average.
_SPED_UP_SOURCE = "simulated"
_MIN_SAMPLES = 5
_HISTORY_LIMIT = 500
_FALLBACK_CLEANING = timedelta(minutes=3)
# A session left open (say a camera died) must not count as hours of occupancy.
_MAX_SESSION = timedelta(hours=6)


def _recent_durations(
    db: Session, restaurant_id: int
) -> tuple[dict[int, list[float]], list[float]]:
    """Past turn times in minutes keyed by table, and past cleaning times in seconds."""
    rows = db.execute(
        select(
            TableSession.table_id,
            TableSession.seated_at,
            TableSession.vacated_at,
            TableSession.cleaned_at,
        )
        .where(
            TableSession.restaurant_id == restaurant_id,
            TableSession.vacated_at.is_not(None),
            TableSession.source != _SPED_UP_SOURCE,
        )
        .order_by(TableSession.seated_at.desc())
        .limit(_HISTORY_LIMIT)
    ).all()
    turns: dict[int, list[float]] = defaultdict(list)
    cleaning: list[float] = []
    for table_id, seated_at, vacated_at, cleaned_at in rows:
        assert vacated_at is not None  # noqa: S101
        turns[table_id].append((vacated_at - seated_at).total_seconds() / 60)
        if cleaned_at is not None:
            cleaning.append((cleaned_at - vacated_at).total_seconds())
    return turns, cleaning


def predict_free_tables(
    db: Session,
    restaurant: Restaurant,
    tables: list[DiningTable],
    seated_at_by_table: dict[int, datetime],
    now: datetime,
) -> list[TablePrediction]:
    """Estimate when each table frees up, soonest first, using this restaurant's own history."""
    turns, cleaning = _recent_durations(db, restaurant.id)
    all_turns = [minutes for values in turns.values() for minutes in values]
    enough_history = len(all_turns) >= _MIN_SAMPLES
    avg_turn = timedelta(
        minutes=mean(all_turns) if enough_history else restaurant.default_turn_minutes
    )
    avg_cleaning = (
        timedelta(seconds=mean(cleaning)) if len(cleaning) >= _MIN_SAMPLES else _FALLBACK_CLEANING
    )

    predictions: list[TablePrediction] = []
    for table in tables:
        seated_at = seated_at_by_table.get(table.id)
        if table.status == TableStatus.free.value:
            eta = now
        elif table.status == TableStatus.needs_cleaning.value:
            eta = now + avg_cleaning
        elif seated_at is not None:
            # A party past the average could leave any time, so never report a time in the past.
            eta = max(seated_at + avg_turn + avg_cleaning, now + avg_cleaning)
        else:
            eta = now + avg_turn
        predictions.append(
            TablePrediction(
                table_id=table.id,
                label=table.label,
                seats=table.seats,
                status=table.status,
                estimated_free_at=eta,
                minutes_until_free=math.ceil((eta - now).total_seconds() / 60),
                based_on_history=enough_history,
            )
        )
    predictions.sort(key=lambda p: p.estimated_free_at)
    return predictions


def _count_weekdays(start: datetime, end: datetime) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    day = start.date()
    while day <= end.date():
        counts[day.weekday()] += 1
        day += timedelta(days=1)
    return counts


def build_analytics(
    db: Session, restaurant: Restaurant, days: int, now: datetime
) -> AnalyticsResponse:
    tz = ZoneInfo(restaurant.timezone)
    start = now - timedelta(days=days)
    sessions = db.scalars(
        select(TableSession).where(
            TableSession.restaurant_id == restaurant.id,
            TableSession.seated_at >= start,
            TableSession.source != _SPED_UP_SOURCE,
        )
    ).all()

    # Covers present per weekday and hour. A party spanning 19:40 to 20:30 counts in both hours.
    cell_totals: dict[tuple[int, int], int] = defaultdict(int)
    turns: list[float] = []
    service_waits: list[float] = []
    cleaning: list[float] = []
    for session in sessions:
        end = session.vacated_at or now
        end = min(end, session.seated_at + _MAX_SESSION)
        cursor = session.seated_at.astimezone(tz).replace(minute=0, second=0, microsecond=0)
        local_end = end.astimezone(tz)
        while cursor <= local_end:
            cell_totals[(cursor.weekday(), cursor.hour)] += session.party_size
            cursor += timedelta(hours=1)
        if session.vacated_at:
            turns.append((session.vacated_at - session.seated_at).total_seconds() / 60)
        if session.first_served_at:
            service_waits.append((session.first_served_at - session.seated_at).total_seconds())
        if session.cleaned_at and session.vacated_at:
            cleaning.append((session.cleaned_at - session.vacated_at).total_seconds())

    weekday_counts = _count_weekdays(start.astimezone(tz), now.astimezone(tz))
    heatmap: list[HeatmapCell] = []
    for (weekday, hour), total in sorted(cell_totals.items()):
        avg = total / max(weekday_counts.get(weekday, 1), 1)
        heatmap.append(
            HeatmapCell(
                weekday=weekday,
                hour=hour,
                avg_covers=round(avg, 1),
                suggested_waiters=math.ceil(avg / restaurant.covers_per_waiter),
            )
        )

    hour_totals: dict[int, int] = defaultdict(int)
    for (_, hour), total in cell_totals.items():
        hour_totals[hour] += total
    hourly = [
        HourlyPoint(hour=hour, avg_covers=round(total / days, 1))
        for hour, total in sorted(hour_totals.items())
    ]
    peak_cell = max(heatmap, key=lambda c: c.avg_covers, default=None)

    alert_rows = db.execute(
        select(Alert.type, func.count(Alert.id))
        .join(TableSession, TableSession.id == Alert.session_id)
        .where(
            Alert.restaurant_id == restaurant.id,
            Alert.created_at >= start,
            TableSession.source != _SPED_UP_SOURCE,
        )
        .group_by(Alert.type)
    ).all()
    alert_counts = {alert_type: count for alert_type, count in alert_rows}

    return AnalyticsResponse(
        days=days,
        is_sample_data=restaurant.is_demo,
        parties=len(sessions),
        covers=sum(s.party_size for s in sessions),
        avg_turn_minutes=round(mean(turns), 1) if turns else None,
        avg_wait_for_service_seconds=round(mean(service_waits)) if service_waits else None,
        avg_cleaning_seconds=round(mean(cleaning)) if cleaning else None,
        waiter_alerts=alert_counts.get(AlertType.waiter.value, 0),
        cleaning_alerts=alert_counts.get(AlertType.cleaning.value, 0),
        peak_hour=peak_cell.hour if peak_cell else None,
        peak_weekday=peak_cell.weekday if peak_cell else None,
        covers_per_waiter=restaurant.covers_per_waiter,
        hourly=hourly,
        heatmap=heatmap,
    )
