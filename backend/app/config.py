from typing import Literal

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

    @model_validator(mode="after")
    def twilio_needs_credentials(self) -> "Settings":
        if self.NOTIFICATION_PROVIDER == "twilio" and not (
            self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN
        ):
            raise ValueError("NOTIFICATION_PROVIDER=twilio needs TWILIO_ACCOUNT_SID and AUTH_TOKEN")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()  # type: ignore[call-arg]
