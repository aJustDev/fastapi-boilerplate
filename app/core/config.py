import os
from importlib.metadata import PackageNotFoundError, version

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the version: pyproject.toml, read from the installed package.
try:
    _APP_VERSION = version("app")
except PackageNotFoundError:
    _APP_VERSION = "0.0.0+unknown"

# SETTINGS_ENV_FILE="" reads no .env file at all. The test suite sets it before importing
# `app`, so a developer's .env.local cannot make local runs differ from CI.
_ENV_FILE = os.getenv("SETTINGS_ENV_FILE", f".env.{os.getenv('ENVIRONMENT', 'local')}") or None

# Placeholder for local use only: validate_secret_key rejects it in any other environment.
_DEFAULT_SECRET_KEY = "change-me-in-production-use-a-32-byte-random-key"  # noqa: S105
# HS256 needs a key of at least 32 bytes (RFC 7518, section 3.2).
_MIN_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"

    APP_NAME: str = "FastAPI App"
    APP_VERSION: str = _APP_VERSION
    APP_DESCRIPTION: str = ""
    ROOT_PATH: str = ""

    # Database — individual vars or full URL
    DB_HOST: str = "localhost"
    DB_PORT: int = 5434
    DB_NAME: str = "app_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"  # noqa: S105 -- local default
    DATABASE_URL: str = ""

    # Database Pool
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # JWT
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_STRICT: str = "5/minute"

    # Metrics
    METRICS_ENABLED: bool = True

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "auto"

    # Webhooks
    WEBHOOK_URL: str = ""

    # Event Bus
    OUTBOX_POLL_INTERVAL_SECONDS: int = 30
    OUTBOX_MAX_RETRIES: int = 5
    OUTBOX_HANDLER_TIMEOUT_SECONDS: int = 30
    OUTBOX_CLEANUP_DAYS: int = 30
    OUTBOX_CLEANUP_BATCH_SIZE: int = 1000

    # Jobs
    JOB_POLL_INTERVAL_SECONDS: int = 15
    JOB_HANDLER_TIMEOUT_SECONDS: int = 60
    # How long a claimed job stays owned by its worker. Past it, any worker may take
    # it back (the owner is assumed dead). Must outlive the handler timeout.
    JOB_LEASE_SECONDS: int = 120

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if self.ENVIRONMENT == "local":
            return self
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be changed from default in non-local environments. "
                "Set the SECRET_KEY environment variable."
            )
        if len(self.SECRET_KEY.encode()) < _MIN_SECRET_KEY_BYTES:
            raise ValueError(
                f"SECRET_KEY must be at least {_MIN_SECRET_KEY_BYTES} bytes. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return self

    @model_validator(mode="after")
    def validate_job_lease(self) -> "Settings":
        # A lease shorter than a running handler would let another worker recover the
        # job while it is still running and execute it twice.
        if self.JOB_LEASE_SECONDS < 2 * self.JOB_HANDLER_TIMEOUT_SECONDS:
            raise ValueError("JOB_LEASE_SECONDS must be at least 2 * JOB_HANDLER_TIMEOUT_SECONDS.")
        return self

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
