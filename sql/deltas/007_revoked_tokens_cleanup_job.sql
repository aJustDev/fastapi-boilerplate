-- 007: Hourly purge of expired token revocations.
-- Apply with: bash sql/apply.sh

INSERT INTO scheduled_jobs (job_name, description, interval_seconds, next_run_at)
VALUES ('revoked_tokens_cleanup', 'Deletes revocations of expired tokens', 3600, now())
ON CONFLICT (job_name) DO NOTHING;
