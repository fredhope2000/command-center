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

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
