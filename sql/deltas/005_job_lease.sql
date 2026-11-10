-- 005: Lease for claimed jobs, so a crashed worker's jobs can be recovered
-- without stealing jobs that other workers are still running.
-- Apply with: bash sql/apply.sh

ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;
