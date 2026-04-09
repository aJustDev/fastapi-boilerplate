# Audit Checklist

Checklist derivado de la [auditoria de calidad](notes/auditoria-calidad.md). Puntuacion global: **8.25 / 10**.

## Puntuaciones por area

| Area                      | Puntuacion | Estado |
|---------------------------|------------|--------|
| Arquitectura y estructura | 9/10       | OK     |
| Calidad del codigo        | 8/10       | OK     |
| Tipado y contratos        | 8.5/10     | OK     |
| Gestion de errores        | 9/10       | OK     |
| Seguridad                 | 7/10       | WARN   |
| Testing                   | 7.5/10     | WARN   |
| Rendimiento               | 8.5/10     | OK     |
| API Design                | 9/10       | OK     |
| Configuracion y DevOps    | 8.5/10     | OK     |
| Documentacion             | 8/10       | OK     |

---

## Top 5 -- Acciones prioritarias

- [x] **[Critico]** Validar SECRET_KEY en produccion (`app/core/config.py`)
- [x] **[Alto]** Implementar token revocation + endpoint POST /v1/auth/logout
- [x] **[Alto]** Validacion de password (min_length=8 + complejidad)
- [x] **[Alto]** Tests de integracion con DB real (testcontainers-python)
- [x] **[Medio]** Validar email con EmailStr en RegisterRequest (`app/schemas/auth/token.py`)

---

## 1. Arquitectura y estructura (9/10)

- [x] Consolidar capas: use cases resuelven directamente (repo) para ops simples, servicios solo para logica compleja (auth). Eliminado ItemService.

## 2. Calidad del codigo (8/10)

- [x] Reemplazar f-strings en logging por lazy formatting (`%s`) -- `app/services/auth.py:23,28-29`
- [x] Activar regla G (flake8-logging-format) en ruff
- [x] Loguear warning en `_apply_filters` cuando un campo de filtro es desconocido -- `app/repos/base.py`
- [x] Renombrar metodo `list()` a `list_paginated()` para eliminar el alias `_list = list` -- `app/repos/base.py`

## 3. Tipado y contratos (8.5/10)

- [x] Usar EmailStr en RegisterRequest.email -- `app/schemas/auth/token.py:5`
- [x] Crear TokenPayload (TypedDict o Pydantic model) para el retorno de decode_token -- `app/core/security/jwt.py:33`
- [x] Tipar mejor `_apply_filters` (dict[str, Any] sin restriccion)

## 4. Gestion de errores (9/10)

- [x] Validacion de password: Field(min_length=8) en RegisterRequest.password

## 5. Seguridad (7/10)

- [x] **[Critico]** Validar que SECRET_KEY != "change-me-in-production" cuando ENVIRONMENT != "local" -- `app/core/config.py:29`
- [x] **[Alto]** Implementar token blacklist/revocation (tabla PostgreSQL) + endpoint /auth/logout
- [x] **[Alto]** Validacion de complejidad de password
- [ ] **[Medio]** Migrar rate limiting a Redis para soporte multi-instancia
- [x] **[Bajo]** Sanitizar PII en logs (no loguear username, usar user_id) -- `app/services/auth.py:23,29`
- [x] Parametrizar NOTIFY en event bus en lugar de f-string -- `app/core/events/bus.py:42-44`

## 6. Testing (7.5/10)

- [x] Tests de integracion reales con testcontainers-python (52 tests en `tests/integration/repos/`). Repos testeados contra PostgreSQL 16 real: CRUD, offset/cursor pagination, filtering, ordering, constraints, relationships.
- [x] Configurar --cov-fail-under=80 en CI -- `pyproject.toml [tool.coverage.report]`
- [x] Renombrar tests/integration/ a tests/functional/ -- tests de contrato HTTP se mantienen (22 tests), nuevo `tests/integration/` para tests con DB real
- [x] ~~Evaluar property-based testing con hypothesis~~ Evaluado: input space de cursores y filtros es acotado, cubierto con tests explicitos + integracion real. hypothesis anade complejidad no justificada en un boilerplate.

## 7. Rendimiento (8.5/10)

- [x] Considerar COUNT(*) OVER() window function o count estimado para offset pagination en tablas grandes -- `app/repos/base.py:80-81`
- [ ] ~~Evaluar cache (aiocache o Redis) para endpoints de lectura frecuente~~ Evaluado: pospuesto hasta que Redis entre al stack (ver 5.4). Cache HTTP headers son opcion stack-neutral pero el beneficio es didactico, no practico para el boilerplate.

## 8. API Design (9/10)

- [x] Verificar que login cumple OAuth2 form standard (application/x-www-form-urlencoded)
- [x] ~~Evaluar incluir _links (next/prev/self) en respuestas paginadas~~ Evaluado: las respuestas ya incluyen los campos necesarios para construir URLs (page/page_size/total_pages para offset; next_cursor para cursor). Agregar _links requiere inyectar Request en la capa de schemas, rompiendo la separacion actual. HATEOAS nivel 3 no justifica la complejidad en un boilerplate.

## 9. Configuracion y DevOps (8.5/10)

- [x] Añadir Dependabot o Renovate para actualizacion automatica de dependencias
- [ ] ~~Añadir paso de build de imagen Docker en CI (validar que compila)~~ Evaluado: trivial y especifico de cada proyecto. No aporta valor didactico al boilerplate.
- [ ] ~~Evaluar stage de deploy en CI~~ Evaluado: un boilerplate no tiene destino de deploy. Cada proyecto definira su propia infra.
- [ ] ~~Considerar docker-compose para staging/production~~ Evaluado: produccion real usa orquestadores (K8s, ECS). El compose actual ya soporta ENVIRONMENT para cambiar env files.
- [ ] ~~Evaluar migracion a Alembic para tracking de migrations~~ Evaluado: el proyecto usa SQL puro con asyncpg, no ORM. El sistema actual (schema.sql + deltas) es explicito y didactico. Si se adopta SQLAlchemy ORM, Alembic seria la eleccion natural.

## 10. Documentacion (8/10)

- [ ] Crear directorio docs/decisions/ con ADRs para decisiones arquitectonicas clave
- [ ] Añadir docstrings en metodos publicos de AuthService e ItemService
