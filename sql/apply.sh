#!/usr/bin/env bash
# Applies pending delta migrations in order.
# Tracks applied migrations in _schema_migrations table.
# Reads DB connection from .env.{ENVIRONMENT} or environment variables.
# Usage: bash sql/apply.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load env file if it exists
ENV_FILE="$PROJECT_DIR/.env.${ENVIRONMENT:-local}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

DB_NAME="${DB_NAME:-app_db}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5434}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
DELTAS_DIR="$SCRIPT_DIR/deltas"

export PGPASSWORD="$DB_PASSWORD"

run_psql() {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -A "$@"
}

# Ensure migration tracking table exists
run_psql -c "
    CREATE TABLE IF NOT EXISTS _schema_migrations (
        filename    TEXT        PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
"

applied=0
for delta_file in "$DELTAS_DIR"/*.sql; do
    [ -f "$delta_file" ] || continue
    filename="$(basename "$delta_file")"

    already_applied=$(run_psql -c "SELECT COUNT(*) FROM _schema_migrations WHERE filename = '$filename';")
    if [ "$already_applied" -gt 0 ]; then
        continue
    fi

    echo "🔄 Applying $filename..."
    run_psql -f "$delta_file"
    run_psql -c "INSERT INTO _schema_migrations (filename) VALUES ('$filename');"
    applied=$((applied + 1))
done

if [ "$applied" -eq 0 ]; then
    echo "✅ No pending migrations."
else
    echo "✅ Applied $applied migration(s)."
fi
