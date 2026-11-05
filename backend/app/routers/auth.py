from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.security import (
    auth_rate_limit,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_even_if_password_pending,
    hash_password,
    sha256,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.exceptions import ConflictError, UnauthorizedError
from app.models import RefreshToken, User
from app.models.base import utcnow
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(db: Session, user_id: int) -> TokenPair:
    refresh = create_refresh_token(user_id)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=sha256(refresh),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return TokenPair(access_token=create_access_token(user_id), refresh_token=refresh)


@router.post(
    "/register",
    status_code=201,
    response_model=UserResponse,
    dependencies=[Depends(auth_rate_limit)],
)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> User:
    email = req.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("An account with this email already exists")
    user = User(email=email, hashed_password=hash_password(req.password), full_name=req.full_name)
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    stored_hash = user.hashed_password if user else None
    if not verify_password(form.password, stored_hash) or user is None or not user.is_active:
        raise UnauthorizedError("Incorrect email or password")
    return _issue_tokens(db, user.id)


@router.post("/refresh", response_model=TokenPair)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    user_id = decode_token(req.refresh_token, "refresh")
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == sha256(req.refresh_token))
    )
    if user_id is None or stored is None or stored.expires_at <= utcnow():
        raise UnauthorizedError("Invalid refresh token")
    if stored.revoked:
        # A used token came back, so it may have been stolen. End every session for this user.
        db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True))
        db.commit()
        raise UnauthorizedError("Invalid refresh token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")
    stored.revoked = True
    return _issue_tokens(db, user_id)


@router.post("/logout", status_code=204)
def logout(req: RefreshRequest, db: Session = Depends(get_db)) -> None:
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == sha256(req.refresh_token))
    )
    if stored:
        stored.revoked = True
        db.commit()


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_user_even_if_password_pending)) -> User:
    return user


@router.post("/change-password", response_model=TokenPair, dependencies=[Depends(auth_rate_limit)])
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_user_even_if_password_pending),
    db: Session = Depends(get_db),
) -> TokenPair:
    if not verify_password(req.current_password, user.hashed_password):
        raise UnauthorizedError("Your current password is incorrect")
    if req.new_password == req.current_password:
        raise ConflictError("Choose a different password")
    user.hashed_password = hash_password(req.new_password)
    user.must_change_password = False
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    return _issue_tokens(db, user.id)
