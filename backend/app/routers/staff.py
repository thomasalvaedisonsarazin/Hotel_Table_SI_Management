import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth.access import (
    Access,
    Role,
    active_member,
    get_access,
    get_manager_access,
)
from app.auth.security import RateLimiter, hash_password
from app.database import get_db
from app.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import (
    Alert,
    AlertDelivery,
    Channel,
    DiningTable,
    PushDevice,
    RefreshToken,
    StaffMember,
    StaffRole,
    User,
)
from app.models.base import utcnow
from app.schemas.staff import (
    DeliveryResponse,
    MyAlertsUpdate,
    NotificationStatus,
    StaffCreate,
    StaffCreated,
    StaffResponse,
    StaffUpdate,
    TemporaryPassword,
    TestSendResult,
)
from app.services.hub import hub
from app.services.notifications import (
    AlertMessage,
    get_provider,
    messages_used_today,
    send_test_push,
)
from app.services.push import get_push_sender

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["staff"])

test_send_limit = RateLimiter(per_minute=5)


def _response(db: Session, member: StaffMember, user: User, owner_id: int) -> StaffResponse:
    response = StaffResponse.model_validate(member)
    response.push_devices = (
        db.scalar(select(func.count(PushDevice.id)).where(PushDevice.user_id == user.id)) or 0
    )
    response.full_name = user.full_name
    response.email = user.email
    response.is_owner = user.id == owner_id
    return response


def _get_member(db: Session, restaurant_id: int, member_id: int) -> tuple[StaffMember, User]:
    row = db.execute(
        select(StaffMember, User)
        .join(User, User.id == StaffMember.user_id)
        .where(StaffMember.id == member_id, StaffMember.restaurant_id == restaurant_id)
    ).first()
    if row is None:
        raise NotFoundError("Staff member")
    return row[0], row[1]


def _check_can_manage(access: Access, target_role: str) -> None:
    """Managers look after staff. Only the owner can add, change or remove a manager."""
    if access.role is not Role.owner and target_role == StaffRole.manager.value:
        raise ForbiddenError("Only the owner can manage managers")


def _check_consent(phone: str | None, consented: bool, sms: bool, whatsapp: bool) -> None:
    if not (sms or whatsapp):
        return
    if not phone:
        raise ConflictError("Add a phone number before turning on message alerts")
    if not consented:
        raise ConflictError("Confirm this person agreed to receive alerts first")


def _revoke_sessions(db: Session, user_id: int) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True))


def _temporary_password() -> str:
    return secrets.token_urlsafe(9)


@router.get("/staff", response_model=list[StaffResponse])
def list_staff(
    access: Access = Depends(get_manager_access), db: Session = Depends(get_db)
) -> list[StaffResponse]:
    rows = db.execute(
        select(StaffMember, User)
        .join(User, User.id == StaffMember.user_id)
        .where(StaffMember.restaurant_id == access.restaurant.id)
        .order_by(StaffMember.is_active.desc(), User.full_name)
    ).all()
    return [_response(db, m, u, access.restaurant.owner_id) for m, u in rows]


@router.post("/staff", status_code=201, response_model=StaffCreated)
def create_staff(
    req: StaffCreate,
    access: Access = Depends(get_manager_access),
    db: Session = Depends(get_db),
) -> StaffCreated:
    _check_can_manage(access, req.role)
    _check_consent(req.phone, req.alerts_consented, req.notify_sms, req.notify_whatsapp)
    email = req.email.lower()
    owner = db.get(User, access.restaurant.owner_id)
    is_owner_alerts = owner is not None and owner.email == email and access.role is Role.owner

    temporary: str | None = None
    if is_owner_alerts and owner is not None:
        # The owner already has a login and only wants the alerts on their own phone.
        user = owner
        if db.scalar(
            select(StaffMember.id).where(
                StaffMember.restaurant_id == access.restaurant.id, StaffMember.user_id == user.id
            )
        ):
            raise ConflictError("You're already on the staff list")
    else:
        if db.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("An account with this email already exists")
        temporary = _temporary_password()
        user = User(
            email=email,
            full_name=req.full_name,
            hashed_password=hash_password(temporary),
            is_staff_account=True,
            must_change_password=True,
        )
        db.add(user)
        db.flush()

    member = StaffMember(
        restaurant_id=access.restaurant.id,
        user_id=user.id,
        role=StaffRole.manager.value if is_owner_alerts else req.role,
        phone=req.phone,
        alerts_consented=req.alerts_consented,
        notify_sms=req.notify_sms,
        notify_whatsapp=req.notify_whatsapp,
        notify_waiter_alerts=req.notify_waiter_alerts,
        notify_cleaning_alerts=req.notify_cleaning_alerts,
    )
    db.add(member)
    db.commit()
    response = _response(db, member, user, access.restaurant.owner_id)
    return StaffCreated(**response.model_dump(), temporary_password=temporary)


@router.patch("/staff/{member_id}", response_model=StaffResponse)
def update_staff(
    member_id: int,
    req: StaffUpdate,
    access: Access = Depends(get_manager_access),
    db: Session = Depends(get_db),
) -> StaffResponse:
    member, user = _get_member(db, access.restaurant.id, member_id)
    _check_can_manage(access, member.role)
    if req.role is not None:
        _check_can_manage(access, req.role)

    changes = req.model_dump(exclude_unset=True)
    is_owner = user.id == access.restaurant.owner_id
    if is_owner and (changes.get("is_active") is False or "role" in changes):
        changes.pop("role", None)
        changes.pop("is_active", None)

    if (
        "phone" in changes
        and changes["phone"] != member.phone
        and "alerts_consented" not in changes
    ):
        # Consent was given for the old number, and this may be a different person's phone.
        changes["alerts_consented"] = False
        changes["notify_sms"] = False
        changes["notify_whatsapp"] = False

    if "full_name" in changes and changes["full_name"]:
        user.full_name = changes["full_name"]
    changes.pop("full_name", None)

    for field, value in changes.items():
        if value is not None or field == "phone":
            setattr(member, field, value)

    if not member.phone or not member.alerts_consented:
        if changes.get("notify_sms") or changes.get("notify_whatsapp"):
            _check_consent(member.phone, member.alerts_consented, True, True)
        member.notify_sms = False
        member.notify_whatsapp = False

    if "is_active" in changes and not is_owner:
        active = bool(changes["is_active"])
        user.is_active = active
        if not active:
            _revoke_sessions(db, user.id)
    db.commit()
    if changes.get("is_active") is False and not is_owner:
        hub.kick(access.restaurant.id, user.id)
    return _response(db, member, user, access.restaurant.owner_id)


@router.post("/staff/{member_id}/reset-password", response_model=TemporaryPassword)
def reset_password(
    member_id: int,
    access: Access = Depends(get_manager_access),
    db: Session = Depends(get_db),
) -> TemporaryPassword:
    member, user = _get_member(db, access.restaurant.id, member_id)
    _check_can_manage(access, member.role)
    if user.id == access.restaurant.owner_id:
        raise ForbiddenError("Use your own profile to change your password")
    temporary = _temporary_password()
    user.hashed_password = hash_password(temporary)
    user.must_change_password = True
    _revoke_sessions(db, user.id)
    db.commit()
    return TemporaryPassword(temporary_password=temporary)


@router.post(
    "/staff/{member_id}/test-alert",
    response_model=list[TestSendResult],
    dependencies=[Depends(test_send_limit)],
)
def send_test_alert(
    member_id: int,
    access: Access = Depends(get_manager_access),
    db: Session = Depends(get_db),
) -> list[TestSendResult]:
    if access.restaurant.is_demo:
        raise ConflictError("Demo restaurants never send real messages")
    member, _ = _get_member(db, access.restaurant.id, member_id)
    channels = (
        [
            channel
            for channel, enabled in (
                (Channel.sms, member.notify_sms),
                (Channel.whatsapp, member.notify_whatsapp),
            )
            if enabled
        ]
        if member.phone and member.alerts_consented
        else []
    )
    has_app = member.notify_push and db.scalar(
        select(PushDevice.id).where(PushDevice.user_id == member.user_id).limit(1)
    )
    if not channels and not has_app:
        raise ConflictError("Turn on message alerts or install the app for this person first")
    provider = get_provider()
    message = AlertMessage(
        restaurant=access.restaurant.name, table="TEST", issue="is a test alert, no action needed"
    )
    results = []
    for channel in channels:
        sent = provider.send(channel, member.phone or "", message)
        status = provider.delivered_status.value if sent.ok else "failed"
        results.append(TestSendResult(channel=channel.value, status=status, error=sent.error))
    if has_app:
        push = get_push_sender()
        sent = send_test_push(db, push, member.user_id, message)
        status = push.delivered_status.value if sent.ok else "failed"
        results.append(TestSendResult(channel="push", status=status, error=sent.error))
        db.commit()
    return results


@router.get("/me/alerts", response_model=StaffResponse | None)
def get_my_alerts(
    access: Access = Depends(get_access), db: Session = Depends(get_db)
) -> StaffResponse | None:
    member = active_member(db, access.restaurant.id, access.user.id)
    return _response(db, member, access.user, access.restaurant.owner_id) if member else None


@router.patch("/me/alerts", response_model=StaffResponse)
def update_my_alerts(
    req: MyAlertsUpdate,
    access: Access = Depends(get_access),
    db: Session = Depends(get_db),
) -> StaffResponse:
    member = active_member(db, access.restaurant.id, access.user.id)
    if member is None:
        raise NotFoundError("Staff member")
    if req.on_shift is not None:
        member.on_shift = req.on_shift
    if req.notify_push is not None:
        member.notify_push = req.notify_push
    for field in ("notify_sms", "notify_whatsapp"):
        value = getattr(req, field)
        if value is None:
            continue
        if value and not member.phone:
            raise ConflictError("Ask your manager to add your phone number first")
        setattr(member, field, value)
        if value:
            # Turning it on yourself is your own agreement to receive alerts.
            member.alerts_consented = True
    db.commit()
    return _response(db, member, access.user, access.restaurant.owner_id)


@router.get("/notifications", response_model=NotificationStatus)
def notification_status(
    access: Access = Depends(get_manager_access), db: Session = Depends(get_db)
) -> NotificationStatus:
    restaurant = access.restaurant
    provider = get_provider()
    rows = db.execute(
        select(AlertDelivery, User.full_name, DiningTable.label, Alert.type)
        .join(StaffMember, StaffMember.id == AlertDelivery.member_id)
        .join(User, User.id == StaffMember.user_id)
        .join(Alert, Alert.id == AlertDelivery.alert_id)
        .join(DiningTable, DiningTable.id == Alert.table_id)
        .where(AlertDelivery.restaurant_id == restaurant.id)
        .order_by(AlertDelivery.created_at.desc(), AlertDelivery.id.desc())
        .limit(30)
    ).all()
    return NotificationStatus(
        provider=provider.name,
        can_send_sms=provider.can_send(Channel.sms),
        can_send_whatsapp=provider.can_send(Channel.whatsapp),
        can_send_push=get_push_sender().configured,
        is_demo=restaurant.is_demo,
        sent_last_24h=messages_used_today(db, restaurant.id, utcnow()),
        daily_limit=restaurant.daily_message_limit,
        recent=[
            DeliveryResponse(
                id=delivery.id,
                created_at=delivery.created_at,
                member_name=name or "Unnamed",
                table_label=label,
                alert_type=alert_type,
                channel=delivery.channel,
                status=delivery.status,
                attempts=delivery.attempts,
                error=delivery.error,
            )
            for delivery, name, label, alert_type in rows
        ],
    )
