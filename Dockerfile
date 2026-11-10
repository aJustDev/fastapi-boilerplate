# syntax=docker/dockerfile:1.7

# -- Builder --------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# The project itself is installed in a separate step so importlib.metadata can read
# its version (APP_VERSION); dependencies stay cached while only the code changes.
COPY app ./app
RUN uv pip install --no-deps . --python /build/.venv/bin/python

# -- Runtime --------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    ENVIRONMENT=production \
    PATH="/build/.venv/bin:$PATH" \
    PYTHONPATH=/app

WORKDIR /app

# Nothing installs packages at runtime: pip only widens the attack surface.
RUN python -m pip uninstall -y pip setuptools wheel

COPY --from=builder /build/.venv /build/.venv

# Allow-list, not `COPY . .`: with a deny-list every new file lands in the image unless
# someone remembers .dockerignore. Adding a path here means it is needed at runtime.
# tests/unit/test_dockerfile_runtime_copy.py keeps this list honest.
COPY main.py alembic.ini ./
COPY app ./app
# The image also applies its own migrations (`alembic upgrade head`, see docker-compose.yml).
COPY migrations ./migrations

RUN groupadd -g 1000 appgroup \
 && useradd -u 1000 -g appgroup -s /usr/sbin/nologin appuser \
 && chown -R appuser:appgroup /app

USER 1000:1000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health/liveness')"]

ENTRYPOINT ["uvicorn"]
CMD ["main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
