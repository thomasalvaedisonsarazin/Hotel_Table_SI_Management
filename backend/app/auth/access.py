"""Who can do what in a restaurant: owner, manager or staff."""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.exceptions import ForbiddenError, NotFoundError
from app.models import Restaurant, StaffMember, User


class Role(StrEnum):
    owner = "owner"
    manager = "manager"
    staff = "staff"


def active_member(db: Session, restaurant_id: int, user_id: int) -> StaffMember | None:
    return db.scalar(
        select(StaffMember).where(
            StaffMember.restaurant_id == restaurant_id,
            StaffMember.user_id == user_id,
            StaffMember.is_active.is_(True),
        )
    )


def role_for(db: Session, restaurant: Restaurant, user: User) -> Role | None:
    if restaurant.owner_id == user.id:
        return Role.owner
    member = active_member(db, restaurant.id, user.id)
    return Role(member.role) if member else None


@dataclass
class Access:
    restaurant: Restaurant
    role: Role
    user: User


def get_access(
    restaurant_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Access:
    restaurant = db.get(Restaurant, restaurant_id)
    role = role_for(db, restaurant, user) if restaurant else None
    # Same response for "missing" and "not yours", so ids can't be probed.
    if restaurant is None or role is None:
        raise NotFoundError("Restaurant")
    return Access(restaurant=restaurant, role=role, user=user)


def get_manager_access(access: Access = Depends(get_access)) -> Access:
    if access.role is Role.staff:
        raise ForbiddenError("Only a manager or the owner can do this")
    return access


def get_owner_access(access: Access = Depends(get_access)) -> Access:
    if access.role is not Role.owner:
        raise ForbiddenError("Only the owner can do this")
    return access


def get_member_restaurant(access: Access = Depends(get_access)) -> Restaurant:
    return access.restaurant


def get_manager_restaurant(access: Access = Depends(get_manager_access)) -> Restaurant:
    return access.restaurant


def get_owned_restaurant(access: Access = Depends(get_owner_access)) -> Restaurant:
    return access.restaurant
