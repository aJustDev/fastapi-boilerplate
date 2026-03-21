-- =============================================================
-- Full schema DDL — source of truth
-- Run with: psql -h localhost -U postgres -d app_db -f schema.sql
-- =============================================================

-- Migration tracking
CREATE TABLE IF NOT EXISTS _schema_migrations (
    filename    TEXT        PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── Auth ────────────────────────────────────────────────────

CREATE TABLE users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email           TEXT        NOT NULL,
    username        TEXT        NOT NULL,
    password_hash   TEXT        NOT NULL,
    full_name       TEXT,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,
    created_by      TEXT,
    updated_by      TEXT
);

CREATE UNIQUE INDEX users_email_uq ON users (LOWER(email));
CREATE UNIQUE INDEX users_username_uq ON users (LOWER(username));
CREATE INDEX users_is_active_idx ON users (is_active) WHERE is_active = TRUE;

CREATE TABLE roles (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE permissions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX user_roles_role_id_idx ON user_roles (role_id);

CREATE TABLE role_permissions (
    role_id       BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE INDEX role_permissions_permission_id_idx ON role_permissions (permission_id);

-- ─── Items ───────────────────────────────────────────────────

CREATE TABLE items (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT        NOT NULL,
    description TEXT,
    category    TEXT        NOT NULL DEFAULT 'general',
    priority    INT         NOT NULL DEFAULT 0,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    owner_id    BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    created_by  TEXT,
    updated_by  TEXT
);

CREATE INDEX items_owner_id_idx ON items (owner_id);
CREATE INDEX items_category_idx ON items (category);
CREATE INDEX items_priority_idx ON items (priority);
CREATE INDEX items_is_active_idx ON items (is_active) WHERE is_active = TRUE;
CREATE INDEX items_created_at_idx ON items (created_at);

-- ─── Events ────────────────────────────────────────────────────

CREATE TABLE outbox_events (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id    UUID,
    correlation_id  UUID,
    event_type      VARCHAR(255)    NOT NULL,
    payload         JSONB           NOT NULL DEFAULT '{}',
    status          VARCHAR(20)     NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'PROCESSED', 'FAILED')),
    retry_count     INT             NOT NULL DEFAULT 0,
    max_retries     INT             NOT NULL DEFAULT 5,
    scheduled_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    handler_state   JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX outbox_events_pending_idx
    ON outbox_events (scheduled_at)
    WHERE status = 'PENDING';

CREATE INDEX outbox_events_aggregate_idx
    ON outbox_events (aggregate_id)
    WHERE aggregate_id IS NOT NULL;

CREATE INDEX outbox_events_correlation_idx
    ON outbox_events (correlation_id)
    WHERE correlation_id IS NOT NULL;
