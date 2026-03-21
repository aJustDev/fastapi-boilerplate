-- Per-handler execution tracking for selective retry.
-- Stores which handlers succeeded so they can be skipped on retry.

ALTER TABLE outbox_events
    ADD COLUMN handler_state JSONB NOT NULL DEFAULT '{}';
