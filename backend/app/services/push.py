"""Rings the Android app through Firebase Cloud Messaging, which is free per message."""

import logging
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx
import jwt

from app.config import settings
from app.models import DeliveryStatus

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_LIFETIME_SECONDS = 3600
# The phone only rings for a message that arrives while it is still useful.
_MESSAGE_TTL = "600s"


@dataclass
class PushResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None
    retryable: bool = False
    unregistered: bool = False


class PushSender(Protocol):
    name: str
    delivered_status: DeliveryStatus

    @property
    def configured(self) -> bool: ...

    def send(self, token: str, data: dict[str, str]) -> PushResult: ...


class LogPushSender:
    """Used until Firebase is set up. Nothing leaves the server."""

    name = "log"
    delivered_status = DeliveryStatus.logged
    configured = False

    def send(self, token: str, data: dict[str, str]) -> PushResult:
        logger.info("Would ring a phone: %s", data.get("kind"))
        return PushResult(ok=True)


class FcmPushSender:
    name = "firebase"
    delivered_status = DeliveryStatus.sent
    configured = True

    def __init__(self, account: dict[str, Any], client: httpx.Client | None = None) -> None:
        self._account = account
        self._client = client or httpx.Client(timeout=10)
        self._url = f"https://fcm.googleapis.com/v1/projects/{account['project_id']}/messages:send"
        self._token = ""
        self._token_expires = 0.0
        self._lock = threading.Lock()

    def _access_token(self) -> str:
        with self._lock:
            now = time.time()
            if self._token and now < self._token_expires - 60:
                return self._token
            token_uri = self._account.get("token_uri", "https://oauth2.googleapis.com/token")
            assertion = jwt.encode(
                {
                    "iss": self._account["client_email"],
                    "scope": _SCOPE,
                    "aud": token_uri,
                    "iat": int(now),
                    "exp": int(now) + _TOKEN_LIFETIME_SECONDS,
                },
                self._account["private_key"],
                algorithm="RS256",
            )
            response = self._client.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            body = response.json()
            self._token = str(body["access_token"])
            self._token_expires = now + float(body.get("expires_in", _TOKEN_LIFETIME_SECONDS))
            return self._token

    def send(self, token: str, data: dict[str, str]) -> PushResult:
        try:
            access_token = self._access_token()
        except httpx.HTTPStatusError as exc:
            logger.warning("Firebase refused the login: HTTP %s", exc.response.status_code)
            return PushResult(
                ok=False,
                error="Firebase refused the server's login",
                retryable=exc.response.status_code >= 500,
            )
        except httpx.HTTPError as exc:
            logger.warning("Could not log in to Firebase: %s", type(exc).__name__)
            return PushResult(ok=False, error="Could not reach Firebase", retryable=True)

        try:
            response = self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "message": {
                        "token": token,
                        # Data only, so the app itself rings instead of Android showing
                        # a quiet notification. High priority wakes a sleeping phone.
                        "data": data,
                        "android": {"priority": "HIGH", "ttl": _MESSAGE_TTL},
                    }
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Firebase request failed: %s", type(exc).__name__)
            return PushResult(ok=False, error="Could not reach Firebase", retryable=True)

        if response.status_code == 200:
            return PushResult(ok=True, message_id=str(response.json().get("name", ""))[-64:])
        logger.warning("Firebase rejected a message with HTTP %s", response.status_code)
        if response.status_code == 404:
            return PushResult(ok=False, error="The app is no longer installed", unregistered=True)
        if response.status_code == 401:
            # Most likely our saved login was cancelled, so get a new one next time.
            self._token = ""
        return PushResult(
            ok=False,
            error=f"Firebase returned HTTP {response.status_code}",
            retryable=response.status_code in (401, 429) or response.status_code >= 500,
        )


@lru_cache
def get_push_sender() -> PushSender:
    account = settings.firebase_service_account
    return FcmPushSender(account) if account else LogPushSender()
