-- Transactional Outbox Event Bus
-- Creates the outbox_events table for the persistent event bus pattern.

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
    processed_at    TIMESTAMPTZ
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
