import os
from importlib.metadata import PackageNotFoundError, version

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

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
    # No default on purpose. "local" is the only value that accepts the placeholder
    # SECRET_KEY and the wildcard hosts: falling back to it would switch every validator
    # below off in the deployment that forgot to set the variable. Development gets it
    # from .env.local; the Docker image sets ENVIRONMENT=production.
    ENVIRONMENT: str

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
    # Recycle connections older than this, before a proxy or the server drops them.
    DB_POOL_RECYCLE: int = 1800
    # Seconds to open a connection. asyncpg waits 60 s by default, and an unreachable
    # host often does not refuse but drops the packets, so every attempt waits that long.
    DB_CONNECT_TIMEOUT: int = 10
    # Client-side limit for one statement, and server-side limits for a query and for
    # waiting on a lock: a stuck query or a long lock must not hold a request forever.
    DB_COMMAND_TIMEOUT: int = 30
    DB_STATEMENT_TIMEOUT_MS: int = 30_000
    DB_LOCK_TIMEOUT_MS: int = 5_000

    # JWT
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:4200"]

    # Hosts the API answers to (Host header); requests for any other host get a 400.
    ALLOWED_HOSTS: list[str] = ["*"]
    # Proxies whose X-Forwarded-For/-Proto are trusted. Only them: anyone else could
    # forge the client IP that rate limits and logs see. Addresses or subnets separated
    # by commas; empty trusts nobody (no proxy in front). Outside local it has to be
    # stated: behind a proxy that is not listed, every client shares the proxy's address
    # and therefore one rate-limit bucket.
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"

    # Security headers (CSP, nosniff, frame options...). Disable only when a reverse
    # proxy already adds them. HSTS only behind HTTPS.
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_ENABLED: bool = False
    HSTS_MAX_AGE: int = 31536000

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_STRICT: str = "5/minute"

    # Metrics. With a token, /v1/metrics requires `Authorization: Bearer <token>`.
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""

    # Swagger UI, ReDoc and /openapi.json. Off unless turned on: they describe the whole
    # API to whoever can reach it.
    DOCS_ENABLED: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "auto"

    # Webhooks
    WEBHOOK_URL: str = ""

    # Background workers. Both run inside every API process by default; turn them off
    # here and run `python -m app.cli worker` to give them a process of their own.
    OUTBOX_WORKER_ENABLED: bool = True
    JOB_WORKER_ENABLED: bool = True

    # Event Bus
    OUTBOX_POLL_INTERVAL_SECONDS: int = 30
    # Attempts before an event is FAILED and waits for a manual replay. The wait doubles
    # each time (2 s, 4 s, ...): 12 attempts span a little over an hour, enough to ride
    # out the restart or the short outage of whatever a handler calls.
    OUTBOX_MAX_RETRIES: int = 12
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
    def validate_network_exposure(self) -> "Settings":
        if self.ENVIRONMENT == "local":
            return self
        if not self.ALLOWED_HOSTS or "*" in self.ALLOWED_HOSTS:
            raise ValueError(
                "ALLOWED_HOSTS must be an explicit list outside local; '*' is not allowed."
            )
        if not self.ALLOWED_ORIGINS or "*" in self.ALLOWED_ORIGINS:
            raise ValueError("ALLOWED_ORIGINS must list the exact frontend origins outside local.")
        if self.FORWARDED_ALLOW_IPS.strip() == "*":
            raise ValueError(
                'FORWARDED_ALLOW_IPS must not be "*" outside local: any client could forge '
                "X-Forwarded-For. Set the address or subnet of the reverse proxy."
            )
        if "FORWARDED_ALLOW_IPS" not in self.model_fields_set:
            raise ValueError(
                "FORWARDED_ALLOW_IPS must be set outside local: the address or subnet of the "
                "reverse proxy, or empty if clients connect to the API directly. Left to its "
                "default behind a proxy, every client would share one rate limit."
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
            # URL.create escapes what an f-string would not: a password with "@", "/" or
            # "#" in it would otherwise be read as part of the host.
            self.DATABASE_URL = URL.create(
                "postgresql+asyncpg",
                username=self.DB_USER,
                password=self.DB_PASSWORD,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            ).render_as_string(hide_password=False)
        elif "sslmode=" in self.DATABASE_URL:
            raise ValueError(
                'DATABASE_URL: the asyncpg driver takes "ssl=require", not "sslmode=require".'
            )
        return self

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
