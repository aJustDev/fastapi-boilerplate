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
- [ ] **[Alto]** Tests de integracion con DB real (testcontainers-python)
- [x] **[Medio]** Validar email con EmailStr en RegisterRequest (`app/schemas/auth/token.py`)

---

## 1. Arquitectura y estructura (9/10)

- [ ] Evaluar consolidar services/ y use_cases/ en una sola capa para CRUD simples, reservando use cases para orquestaciones multi-servicio

## 2. Calidad del codigo (8/10)

- [x] Reemplazar f-strings en logging por lazy formatting (`%s`) -- `app/services/auth.py:23,28-29`
- [ ] Activar regla G (flake8-logging-format) en ruff
- [ ] Loguear warning en `_apply_filters` cuando un campo de filtro es desconocido -- `app/repos/base.py:208-209`
- [ ] Renombrar metodo `list()` a `list_paginated()` para eliminar el alias `_list = list` -- `app/repos/base.py:11`

## 3. Tipado y contratos (8.5/10)

- [x] Usar EmailStr en RegisterRequest.email -- `app/schemas/auth/token.py:5`
- [x] Crear TokenPayload (TypedDict o Pydantic model) para el retorno de decode_token -- `app/core/security/jwt.py:33`
- [ ] Tipar mejor `_apply_filters` (dict[str, Any] sin restriccion)

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

- [ ] Tests de integracion reales con testcontainers-python o PostgreSQL en CI
- [ ] Configurar --cov-fail-under=80 en CI
- [ ] Renombrar tests/integration/ a tests/functional/ para evitar confusion semantica
- [ ] Evaluar property-based testing con hypothesis para validaciones complejas (cursores, filtros)

## 7. Rendimiento (8.5/10)

- [ ] Considerar COUNT(*) OVER() window function o count estimado para offset pagination en tablas grandes -- `app/repos/base.py:80-81`
- [ ] Evaluar cache (aiocache o Redis) para endpoints de lectura frecuente

## 8. API Design (9/10)

- [ ] Verificar que login cumple OAuth2 form standard (application/x-www-form-urlencoded)
- [ ] Evaluar incluir _links (next/prev/self) en respuestas paginadas

## 9. Configuracion y DevOps (8.5/10)

- [ ] Añadir Dependabot o Renovate para actualizacion automatica de dependencias
- [ ] Añadir paso de build de imagen Docker en CI (validar que compila)
- [ ] Evaluar stage de deploy en CI
- [ ] Considerar docker-compose para staging/production
- [ ] Evaluar migracion a Alembic para tracking de migrations

## 10. Documentacion (8/10)

- [ ] Crear directorio docs/decisions/ con ADRs para decisiones arquitectonicas clave
- [ ] Añadir docstrings en metodos publicos de AuthService e ItemService
