# Docker

A two-stage image that contains the locked virtualenv and only the files the app reads at
runtime, runs as a non-root user in UTC, and serves the API with uvicorn. `docker-compose.yml`
runs PostgreSQL, the migrations and the API for local work.

## How the image is built

```mermaid
flowchart LR
    subgraph builder ["builder: python 3.14-slim"]
        L["uv.lock"] -->|uv sync --frozen --no-dev| V["/build/.venv"]
        A["app/"] -->|uv pip install .| V
    end
    subgraph runtime ["runtime: python 3.14-slim"]
        V2["/build/.venv"] --- F["main.py, app/, alembic.ini, migrations/"]
    end
    V --> V2
```

- **builder** installs the locked dependencies, then the project itself (so `importlib.metadata`
  gives `APP_VERSION`). Dependencies are installed before the code is copied, so a code change
  reuses the dependency layer. `uv` comes from a pinned image tag.
- **runtime** copies the virtualenv and an explicit list of paths (`main.py`, `alembic.ini`,
  `app/`, `migrations/`); never `COPY . .`. pip, setuptools and wheel are removed. It runs as
  uid/gid 1000 with `TZ=UTC` and `ENVIRONMENT=production`, exposes 8000 and has a `HEALTHCHECK` on
  `/v1/health/liveness`.
- `.dockerignore` keeps the build context small and lets no `.env.*` file in except
  `.env.example`.

## Usage

```bash
docker build -t app .
docker run --env-file .env.prod -p 8000:8000 app                 # the API
docker run --env-file .env.prod --entrypoint alembic app upgrade head   # the migrations
```

Local development with compose. Every service reads `.env.local` (`.env.<ENVIRONMENT>`), so
create it first:

```bash
cp .env.example .env.local
docker compose up db -d        # PostgreSQL 18 on 127.0.0.1:5434
docker compose up --build      # db, then migrate (alembic upgrade head), then api
docker compose exec api python scripts/seed_dev.py
```

| Service | Role |
|---|---|
| `db` | `postgres:18-alpine`, volume `pgdata18`, healthcheck with `pg_isready`, published on loopback only. Its user, password and database are `DB_USER`, `DB_PASSWORD` and `DB_NAME` of the env file, the same values the API connects with |
| `migrate` | The API image running `alembic upgrade head`, then exits |
| `api` | Starts after `migrate` succeeded; mounts the repo and runs uvicorn with `--reload` |

`docker-compose.observability.yml` adds Prometheus and Grafana (`docs/metrics.md`).

To add a file to the image, add it to the runtime `COPY` list, with a comment if the reason is
not obvious.

## Guarantees and limits

- `tests/unit/test_dockerfile_runtime_copy.py` fails if the runtime stage copies the whole
  context, copies a path that does not exist, or copies a path excluded by `.dockerignore`.
- CI lints the Dockerfile with hadolint; Dependabot proposes base image updates weekly.
- The volume name carries the PostgreSQL major version: a volume created by another major
  version cannot be reused.
- The database keeps the credentials it was created with: after changing `DB_PASSWORD` in the env
  file, recreate the volume (`docker compose down -v`) or change the password in PostgreSQL.
- The host port of `db` is `${DB_PORT:-5434}` from the shell, not from the env file: when
  changing it, export `DB_PORT` for compose and set the same value in `.env.local`.
- A bare `.env` is git-ignored like every `.env.*` except the template.
- The image does not run the migrations on start; run them as a separate step (`docs/migrations.md`).
- uvicorn starts with `--no-proxy-headers` and `--no-server-header`: forwarded headers are read
  by the app from `FORWARDED_ALLOW_IPS` (`docs/security.md`), and the `Server` header is not sent.
- The `HEALTHCHECK` asks for `localhost`; the health endpoints are exempt from `ALLOWED_HOSTS`,
  so it works with the explicit hosts production requires.
- The image runs as `ENVIRONMENT=production`: without a real `SECRET_KEY`, explicit
  `ALLOWED_HOSTS` and `ALLOWED_ORIGINS` it refuses to start (`docs/configuration.md`). Compose sets
  `ENVIRONMENT=local` through the env file.
