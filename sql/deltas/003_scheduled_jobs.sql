-- 003: Scheduled jobs table for recurring tasks
-- Apply with: bash sql/apply.sh

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name         VARCHAR(255)    NOT NULL UNIQUE,
    description      TEXT,
    interval_seconds INT             NOT NULL,
    status           VARCHAR(20)     NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING', 'RUNNING', 'DISABLED')),
    last_run_at      TIMESTAMPTZ,
    next_run_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    last_error       TEXT,
    run_count        INT             NOT NULL DEFAULT 0,
    claimed_by       TEXT,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS scheduled_jobs_pending_idx
    ON scheduled_jobs (next_run_at)
    WHERE status = 'PENDING';
