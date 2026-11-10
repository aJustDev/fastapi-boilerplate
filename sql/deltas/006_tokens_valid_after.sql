-- 006: Per-user cut-off for issued tokens, set when a replayed refresh token
-- reveals that a session was stolen.
-- Apply with: bash sql/apply.sh

ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMPTZ;
