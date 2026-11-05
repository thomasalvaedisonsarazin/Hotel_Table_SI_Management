from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.access import role_for
from app.auth.security import decode_alert_ack_token, get_current_user
from app.database import get_db
from app.exceptions import UnauthorizedError
from app.models import Alert, AlertStatus, PushDevice, Restaurant, User
from app.models.base import utcnow
from app.schemas.staff import AlertAckFromPhone, DeviceRegister
from app.services.hub import publish_floor_changed

router = APIRouter(tags=["devices"])

MAX_DEVICES_PER_USER = 5


@router.post("/devices", status_code=204)
def register_device(
    req: DeviceRegister,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    now = utcnow()
    device = db.scalar(select(PushDevice).where(PushDevice.token == req.token))
    if device:
        # On a shared phone, alerts follow whoever signed in last.
        device.user_id = user.id
        device.last_seen_at = now
    else:
        db.add(PushDevice(user_id=user.id, token=req.token, created_at=now, last_seen_at=now))
    db.flush()
    old_devices = db.scalars(
        select(PushDevice)
        .where(PushDevice.user_id == user.id)
        .order_by(PushDevice.last_seen_at.desc(), PushDevice.id.desc())
        .offset(MAX_DEVICES_PER_USER)
    ).all()
    for old in old_devices:
        db.delete(old)
    db.commit()


@router.post("/devices/unregister", status_code=204)
def unregister_device(
    req: DeviceRegister,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.execute(
        delete(PushDevice).where(PushDevice.token == req.token, PushDevice.user_id == user.id)
    )
    db.commit()


@router.post("/alerts/acknowledge-from-phone", status_code=204)
def acknowledge_from_phone(req: AlertAckFromPhone, db: Session = Depends(get_db)) -> None:
    """The Acknowledge button on a ringing phone. The token in the alert is the permission."""
    decoded = decode_alert_ack_token(req.token)
    if decoded is None:
        raise UnauthorizedError("This alert has expired")
    user_id, alert_id = decoded
    user = db.get(User, user_id)
    alert = db.get(Alert, alert_id)
    restaurant = db.get(Restaurant, alert.restaurant_id) if alert else None
    # Someone removed from the staff since the alert went out can no longer respond to it.
    if not (user and user.is_active and alert and restaurant and role_for(db, restaurant, user)):
        raise UnauthorizedError("This alert has expired")
    if alert.status == AlertStatus.open.value:
        alert.status = AlertStatus.acknowledged.value
        alert.acknowledged_at = utcnow()
        db.commit()
        publish_floor_changed(restaurant.id)
