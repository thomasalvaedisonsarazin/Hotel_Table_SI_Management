import base64
import binascii
import json
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "DineOps SI"
    DATABASE_URL: str
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    ENGINE_ENABLED: bool = True
    ENGINE_TICK_SECONDS: float = 2.0
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    DELIVERY_TICK_SECONDS: float = 3.0

    NOTIFICATION_PROVIDER: Literal["log", "twilio"] = "log"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_SMS_FROM: str = ""
    TWILIO_WHATSAPP_FROM: str = ""
    TWILIO_WHATSAPP_CONTENT_SID: str = ""

    # Rings the Android app. Base64 of the Firebase service account JSON file.
    FIREBASE_SERVICE_ACCOUNT_B64: str = ""
    # Where phones reach this server, like https://app.example.com
    PUBLIC_APP_URL: str = ""

    @model_validator(mode="after")
    def twilio_needs_credentials(self) -> "Settings":
        if self.NOTIFICATION_PROVIDER == "twilio" and not (
            self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN
        ):
            raise ValueError("NOTIFICATION_PROVIDER=twilio needs TWILIO_ACCOUNT_SID and AUTH_TOKEN")
        return self

    @model_validator(mode="after")
    def firebase_needs_valid_settings(self) -> "Settings":
        # Fail at startup. Found later, it would only surface as phones silently not ringing.
        if self.FIREBASE_SERVICE_ACCOUNT_B64:
            account = self.firebase_service_account
            if not (account and {"project_id", "client_email", "private_key"} <= account.keys()):
                raise ValueError("FIREBASE_SERVICE_ACCOUNT_B64 is not a service account file")
            if not self.PUBLIC_APP_URL.startswith("https://"):
                raise ValueError("Firebase alerts need PUBLIC_APP_URL set to an https:// address")
        return self

    @property
    def firebase_service_account(self) -> dict[str, Any] | None:
        if not self.FIREBASE_SERVICE_ACCOUNT_B64:
            return None
        try:
            account = json.loads(base64.b64decode(self.FIREBASE_SERVICE_ACCOUNT_B64))
        except (binascii.Error, ValueError):
            return None
        return account if isinstance(account, dict) else None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()  # type: ignore[call-arg]
