# Development Skill

## System of work

### Before coding
1. Read `docs/architecture.md` for layer responsibilities and conventions
2. Check existing patterns in a similar module (e.g., auth or items)
3. Follow the "Adding a new module" checklist

### Layer rules
- **Routers** only parse HTTP, call use cases, return schemas. No business logic.
- **Use cases** orchestrate services. They are thin — if a use case has >20 lines, the logic should move to a service.
- **Services** own business rules. They receive repos via constructor. They raise domain exceptions.
- **Repos** extend BaseRepo[T]. Override `_base_select()` for eager loading. Configure `map_field` for filtering.
- **Models** use `IntPkMixin` + `AuditMixin`. Use `Mapped[]` annotations, not legacy `Column()`.

### Exception handling
- Raise domain exceptions (`NotFoundError`, `ConflictError`, `AuthenticationError`, etc.)
- Never raise `HTTPException` from services/repos — the global handlers convert domain exceptions to HTTP responses
- Custom exceptions: subclass `UseCaseException` (400-level) or `DomainException` (500-level)

### Testing
- Unit tests: mock repos with `AsyncMock`, test services and use cases in isolation
- Integration tests: use `httpx.AsyncClient` + `ASGITransport`, override `get_session`
- Name: `test_{feature}_{scenario}`

### Before committing
1. Run tests: `uv run pytest`
2. Run linter: `uv run ruff check app/ tests/`
3. Run formatter: `uv run ruff format app/ tests/`

Pre-commit hooks enforce this automatically, but run them manually to catch issues early.

### SQL changes
1. Update `sql/schema.sql` with the new DDL
2. Create `sql/deltas/NNN_description.sql` with the ALTER/CREATE statements
3. Run `bash sql/apply.sh` to apply to existing databases

### Dependencies
- Add to `pyproject.toml` under `[project.dependencies]`
- Pin major versions: `"httpx>=0.28"`
- Run `uv sync` to install after adding
