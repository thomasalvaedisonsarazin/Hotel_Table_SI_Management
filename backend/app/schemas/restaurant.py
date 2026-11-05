from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown timezone") from exc
    return value


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"

    _check_timezone = field_validator("timezone")(_valid_timezone)


class DemoCreate(BaseModel):
    timezone: str = "UTC"

    _check_timezone = field_validator("timezone")(_valid_timezone)


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None
    waiter_alert_seconds: int | None = Field(default=None, ge=10, le=3600)
    cleaning_alert_seconds: int | None = Field(default=None, ge=0, le=3600)
    seat_confirm_seconds: int | None = Field(default=None, ge=0, le=600)
    vacate_confirm_seconds: int | None = Field(default=None, ge=0, le=1800)
    service_confirm_seconds: int | None = Field(default=None, ge=0, le=300)
    clean_confirm_seconds: int | None = Field(default=None, ge=0, le=600)
    default_turn_minutes: int | None = Field(default=None, ge=5, le=480)
    covers_per_waiter: int | None = Field(default=None, ge=1, le=200)
    daily_message_limit: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str | None) -> str | None:
        return _valid_timezone(value) if value is not None else None


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    timezone: str
    is_demo: bool
    simulator_enabled: bool
    has_api_key: bool = False
    my_role: str = "owner"
    daily_message_limit: int
    waiter_alert_seconds: int
    cleaning_alert_seconds: int
    seat_confirm_seconds: int
    vacate_confirm_seconds: int
    service_confirm_seconds: int
    clean_confirm_seconds: int
    default_turn_minutes: int
    covers_per_waiter: int


class ApiKeyResponse(BaseModel):
    api_key: str


class SimulatorToggle(BaseModel):
    enabled: bool


class TableCreate(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    seats: int = Field(default=4, ge=1, le=50)
    x: float = Field(default=10, ge=0, le=100)
    y: float = Field(default=10, ge=0, le=100)


class TableUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=20)
    seats: int | None = Field(default=None, ge=1, le=50)
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)


class TableAction(BaseModel):
    action: Literal["seat", "served", "vacate", "cleaned"]
    party_size: int = Field(default=2, ge=1, le=50)


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    seats: int
    x: float
    y: float
    status: str
    status_changed_at: datetime


class FloorTable(TableResponse):
    party_size: int | None = None
    seated_at: datetime | None = None
    first_served_at: datetime | None = None
    vacated_at: datetime | None = None
    session_source: str | None = None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    table_label: str = ""
    type: str
    status: str
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class WaitlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    party_size: int = Field(ge=1, le=50)


class WaitlistSeat(BaseModel):
    table_id: int


class WaitlistResponse(BaseModel):
    id: int
    name: str
    party_size: int
    status: str
    joined_at: datetime
    seated_at: datetime | None
    table_id: int | None
    estimated_wait_minutes: int | None = None
    suggested_table_id: int | None = None
    suggested_table_label: str | None = None


class TablePrediction(BaseModel):
    table_id: int
    label: str
    seats: int
    status: str
    estimated_free_at: datetime
    minutes_until_free: int
    based_on_history: bool


class FloorResponse(BaseModel):
    server_time: datetime
    restaurant: RestaurantResponse
    tables: list[FloorTable]
    alerts: list[AlertResponse]
    waitlist: list[WaitlistResponse]
    predictions: list[TablePrediction]


class Observation(BaseModel):
    table_id: int
    guest_count: int = Field(ge=0, le=100)
    staff_present: bool = False


class ObservationBatch(BaseModel):
    observations: list[Observation] = Field(min_length=1, max_length=200)


class IngestResult(BaseModel):
    accepted: int
    changed: int


class HeatmapCell(BaseModel):
    weekday: int
    hour: int
    avg_covers: float
    suggested_waiters: int


class HourlyPoint(BaseModel):
    hour: int
    avg_covers: float


class AnalyticsResponse(BaseModel):
    days: int
    is_sample_data: bool
    parties: int
    covers: int
    avg_turn_minutes: float | None
    avg_wait_for_service_seconds: float | None
    avg_cleaning_seconds: float | None
    waiter_alerts: int
    cleaning_alerts: int
    peak_hour: int | None
    peak_weekday: int | None
    covers_per_waiter: int
    hourly: list[HourlyPoint]
    heatmap: list[HeatmapCell]
