"""Imports every module that registers something by being imported.

- ORM models, so Base.metadata knows every table (migrations/env.py, tests).
- Event handlers (`@dispatcher.register`) and job handlers (`@job_registry.register`).

main.py, migrations/env.py and the integration tests import this module. A context that
adds models or handlers adds its import here; nothing else imports handler modules.
It lives outside app/core because it imports the contexts, which core must not do.
"""

import app.auth.jobs.revoked_tokens_cleanup  # noqa: F401
import app.auth.models  # noqa: F401
import app.core.events.models  # noqa: F401
import app.core.jobs.handlers.heartbeat  # noqa: F401
import app.core.jobs.handlers.outbox_cleanup  # noqa: F401
import app.core.jobs.models  # noqa: F401
import app.items.event_handlers.item_events  # noqa: F401
import app.items.models  # noqa: F401
