from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    """All runtime configuration; every field can be set via env var or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./urlshortener.db"
    base_url: str = "http://localhost:8000"

    # Secret for short-code obfuscation and visitor hashing. Rotating it changes
    # every generated short code, so treat it like a database key.
    secret_key: str = _DEV_SECRET
    # Bootstrap credential for POST /api/v1/keys. Empty disables the endpoint.
    admin_api_key: str = ""

    max_url_length: int = 2048
    allow_private_targets: bool = False
    bulk_max_items: int = 100
    max_ttl_seconds: int = 60 * 60 * 24 * 365 * 5

    cache_max_entries: int = 50_000
    cache_ttl_seconds: int = 300

    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 30

    click_queue_size: int = 100_000
    click_batch_size: int = 500
    click_flush_interval: float = 0.5

    # Only enable behind a proxy you control; otherwise X-Forwarded-For is spoofable.
    trust_proxy_headers: bool = False
    geoip_db_path: str = ""

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.env == "production" and self.secret_key == _DEV_SECRET:
            raise ValueError("SECRET_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
