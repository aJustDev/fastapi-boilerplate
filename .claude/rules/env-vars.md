---
name: env-vars
description: Settings. Every field documented in .env.example, safe local defaults, validators for what is only wrong outside local.
paths:
    - app/core/config.py
    - .env.example
---

# Environment variables

Guide: `docs/configuration.md`.

- A new setting is a field in `Settings` with a safe default for local development, and a line
  in `.env.example` (active `KEY=value` or commented `# KEY=`). `ENVIRONMENT` is the one field
  without a default: an unset value must stop the process, not mean `local`.
- A value that is only dangerous in production gets a `model_validator` that skips `local`, and
  a row in the validators table of `docs/configuration.md`.
- Document the setting in the doc of the feature that uses it.
- Tests build `Settings(...)` with explicit values; they never read a `.env` file.

## Enforcement

`tests/unit/core/test_env_example_sync.py` fails when `Settings` and `.env.example` differ.
