#!/usr/bin/env bash
# Runs locally what the CI workflow runs, in the same order. Source of truth:
# .github/workflows/ci.yml; change both together.
#
# Usage:
#   bash scripts/ci-local.sh                     # everything (needs Docker)
#   SKIP_INTEGRATION=1 bash scripts/ci-local.sh  # without Docker

set -uo pipefail

export TZ=UTC
failed=0

step() {
  local name="$1"
  shift
  echo ""
  echo "=== $name ==="
  if "$@"; then
    echo "OK: $name"
  else
    echo "FAILED: $name"
    failed=1
  fi
}

diagrams_up_to_date() {
  for f in docs/img/[!_]*.py; do uv run python "$f" > /dev/null || return 1; done
  [ -z "$(git status --porcelain -- docs/img)" ]
}

step "Lockfile up to date" uv lock --check
step "Ruff check" uv run ruff check app/ tests/ migrations/ scripts/ main.py docs/img/
step "Ruff format check" uv run ruff format --check app/ tests/ migrations/ scripts/ main.py docs/img/
step "Mypy" uv run mypy app/ main.py

single_alembic_head() {
  [ "$(uv run alembic heads | grep -c '(head)')" = "1" ]
}
step "Single Alembic head" single_alembic_head
step "Diagrams up to date" diagrams_up_to_date
step "Dependency CVE audit" uv run pip-audit --skip-editable

if [ "${SKIP_INTEGRATION:-0}" = "1" ]; then
  step "Tests (unit + functional)" uv run pytest --ignore=tests/integration
else
  step "Tests (unit, functional and integration)" uv run pytest --cov=app
fi

echo ""
if [ "$failed" = "0" ]; then
  echo "ALL GREEN: same checks as CI (hadolint runs only in CI)."
else
  echo "FAILURES: do not merge."
  exit 1
fi
