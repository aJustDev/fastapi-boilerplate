# FastAPI Boilerplate

Boilerplate reutilizable para proyectos FastAPI con SQLAlchemy async, JWT auth y arquitectura por capas.

## Stack

- Python 3.13+ / FastAPI / Pydantic v2
- SQLAlchemy 2.x async + asyncpg + PostgreSQL 16
- JWT (PyJWT) + Argon2 password hashing
- Docker + docker-compose

## Setup rápido

```bash
# 1. Levantar PostgreSQL
docker compose up db -d

# 2. Crear esquema e insertar datos iniciales
bash sql/reset.sh

# 3. Instalar dependencias
uv sync --extra dev

# 4. Arrancar la API
ENVIRONMENT=local uv run uvicorn app.main:app --reload

# 5. Abrir docs
open http://localhost:8000/docs
```

## Setup con Docker

```bash
docker compose up --build
bash sql/reset.sh  # en otra terminal
```

## Estructura

```
app/
├── core/           # Config, DB, security, logging, exceptions, lifespan
├── models/         # SQLAlchemy ORM (por dominio: auth/, items/)
├── schemas/        # Pydantic v2 request/response
├── repos/          # Repositorios async con BaseRepo[T]
├── services/       # Lógica de negocio
├── use_cases/      # Orquestadores (coordinan servicios)
├── deps/           # FastAPI dependencies (auth, repos)
└── api/v1/         # Routers HTTP
```

## Auth flow

```bash
# Registrar usuario
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","username":"user1","password":"pass123"}'

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user@test.com","password":"pass123"}'

# Usar token
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# Refresh
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

## Tests

```bash
# Unit tests (sin DB)
pytest tests/unit

# Integration tests (sin DB real, mocks)
pytest tests/integration

# Todos
pytest
```

## SQL migrations

```bash
# Reset completo (drop + schema + seeds)
bash sql/reset.sh

# Aplicar deltas pendientes
bash sql/apply.sh
```

Ver `docs/architecture.md` para la guía completa de cómo añadir un nuevo módulo.
