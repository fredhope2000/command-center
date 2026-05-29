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
    aws_region: str = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "")
    restaurant_photos_s3_bucket: str = os.getenv(
        "RESTAURANT_PHOTOS_S3_BUCKET", "fredhopedotcom"
    )
    restaurant_photos_s3_prefix: str = os.getenv(
        "RESTAURANT_PHOTOS_S3_PREFIX",
        "ec2/command-center"
        if os.getenv("APP_ENV", "development").strip().lower() == "production"
        else "ec2/command-center-dev",
    ).strip("/")
    restaurant_photos_base_url: str = os.getenv(
        "RESTAURANT_PHOTOS_BASE_URL", "https://fredhope.com"
    ).rstrip("/")
    auth_enabled: bool = os.getenv(
        "COMMAND_CENTER_AUTH_ENABLED",
        "true" if os.getenv("APP_ENV", "development").strip().lower() == "production" else "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    password_hash: str = os.getenv("COMMAND_CENTER_PASSWORD_HASH", "")
    auth_secret: str = os.getenv("COMMAND_CENTER_AUTH_SECRET", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_restaurant_model: str = os.getenv(
        "OPENAI_RESTAURANT_MODEL", "gpt-5.4-nano"
    )
    openai_restaurant_qa_model: str = os.getenv(
        "OPENAI_RESTAURANT_QA_MODEL",
        os.getenv("OPENAI_RESTAURANT_MODEL", "gpt-5.4-mini"),
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def restaurant_ai_enabled(self) -> bool:
        return self.is_production and bool(self.openai_api_key)


settings = Settings()
