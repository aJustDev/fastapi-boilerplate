#!/usr/bin/env bash
# Drops and recreates the database, then applies schema + seeds.
# Reads DB connection from .env.{ENVIRONMENT} or environment variables.
# Usage: bash sql/reset.sh

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

export PGPASSWORD="$DB_PASSWORD"

echo "⚠️  Dropping and recreating database '$DB_NAME' on $DB_HOST:$DB_PORT..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
" > /dev/null 2>&1 || true

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;"

echo "📦 Applying schema..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SCRIPT_DIR/schema.sql"

echo "🌱 Applying seeds..."
for seed_file in "$SCRIPT_DIR"/seeds/*.sql; do
    [ -f "$seed_file" ] || continue
    echo "  → $(basename "$seed_file")"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$seed_file"
done

echo "✅ Database '$DB_NAME' reset complete."
