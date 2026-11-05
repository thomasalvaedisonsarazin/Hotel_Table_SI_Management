import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def _check_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    cleaned = re.sub(r"[\s()-]", "", value)
    if not _E164.match(cleaned):
        raise ValueError("Enter the phone number with its country code, like +919876543210")
    return cleaned


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Literal["manager", "staff"] = "staff"
    phone: str | None = None
    alerts_consented: bool = False
    notify_sms: bool = False
    notify_whatsapp: bool = False
    notify_waiter_alerts: bool = True
    notify_cleaning_alerts: bool = True

    _phone = field_validator("phone")(_check_phone)


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["manager", "staff"] | None = None
    phone: str | None = None
    alerts_consented: bool | None = None
    notify_sms: bool | None = None
    notify_whatsapp: bool | None = None
    notify_waiter_alerts: bool | None = None
    notify_cleaning_alerts: bool | None = None
    on_shift: bool | None = None
    is_active: bool | None = None

    _phone = field_validator("phone")(_check_phone)


class MyAlertsUpdate(BaseModel):
    on_shift: bool | None = None
    notify_sms: bool | None = None
    notify_whatsapp: bool | None = None
    notify_push: bool | None = None


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    full_name: str | None = None
    email: str = ""
    is_owner: bool = False
    role: str
    is_active: bool
    phone: str | None
    alerts_consented: bool
    notify_sms: bool
    notify_whatsapp: bool
    notify_waiter_alerts: bool
    notify_cleaning_alerts: bool
    notify_push: bool
    push_devices: int = 0
    on_shift: bool


class StaffCreated(StaffResponse):
    temporary_password: str | None = None


class DeviceRegister(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class AlertAckFromPhone(BaseModel):
    token: str = Field(max_length=1000)


class TemporaryPassword(BaseModel):
    temporary_password: str


class TestSendResult(BaseModel):
    channel: str
    status: str
    error: str | None = None


class DeliveryResponse(BaseModel):
    id: int
    created_at: datetime
    member_name: str
    table_label: str
    alert_type: str
    channel: str
    status: str
    attempts: int
    error: str | None


class NotificationStatus(BaseModel):
    provider: str
    can_send_sms: bool
    can_send_whatsapp: bool
    can_send_push: bool
    is_demo: bool
    sent_last_24h: int
    daily_limit: int
    recent: list[DeliveryResponse]
