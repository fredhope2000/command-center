from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Command Center")
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///instance/dev.sqlite")
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    google_maps_map_id: str = os.getenv("GOOGLE_MAPS_MAP_ID", "")
    auth_enabled: bool = os.getenv(
        "COMMAND_CENTER_AUTH_ENABLED",
        "true" if os.getenv("APP_ENV", "development").strip().lower() == "production" else "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    password_hash: str = os.getenv("COMMAND_CENTER_PASSWORD_HASH", "")
    auth_secret: str = os.getenv("COMMAND_CENTER_AUTH_SECRET", "")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
