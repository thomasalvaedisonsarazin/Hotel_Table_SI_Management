import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.exceptions import RateLimitedError, UnauthorizedError
from app.models import User
from app.models.base import utcnow

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Compared against when an email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = bcrypt.hashpw(b"no-such-user", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    encoded = password.encode()
    # bcrypt raises on input over 72 bytes, and no valid password can be that long.
    matches = bcrypt.checkpw(encoded[:72], (hashed or _DUMMY_HASH).encode())
    return matches and hashed is not None and len(encoded) <= 72


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_api_key() -> str:
    return f"ts_{secrets.token_urlsafe(32)}"


def _encode(user_id: int, kind: str, lifetime: timedelta) -> str:
    payload = {
        "sub": str(user_id),
        "type": kind,
        "exp": utcnow() + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _encode(user_id, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: int) -> str:
    return _encode(user_id, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str) -> int | None:
    """Return the user id if the token is valid and of the expected type."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return int(payload["sub"])


def user_from_access_token(db: Session, token: str) -> User | None:
    user_id = decode_token(token, "access")
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = user_from_access_token(db, token)
    if user is None:
        raise UnauthorizedError("Invalid or expired token")
    return user


class RateLimiter:
    """Per-client, per-process sliding window. Enough for one worker; use Redis beyond that."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        hits = self._hits[client]
        cutoff = time.monotonic() - 60
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= settings.AUTH_RATE_LIMIT_PER_MINUTE:
            raise RateLimitedError()
        hits.append(time.monotonic())


auth_rate_limit = RateLimiter()
