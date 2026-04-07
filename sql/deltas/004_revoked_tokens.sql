CREATE TABLE revoked_tokens (
    jti         UUID        PRIMARY KEY,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX revoked_tokens_expires_at_idx ON revoked_tokens (expires_at);
