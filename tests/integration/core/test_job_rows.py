"""Every job has both halves: a handler in code and a row from the migrations.

One without the other never runs and nothing fails: a typo in a job name would only show
as a table that keeps growing.
"""

import pytest

import app.db_registry  # noqa: F401 -- registers every job handler
from app.core.jobs.registry import job_registry
from app.core.jobs.worker import job_mismatches

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_registered_jobs_and_seeded_rows_match(app_database):
    without_row, without_handler = await job_mismatches()

    assert without_row == [], "add the row of these jobs with a migration"
    assert without_handler == [], "these rows have no handler: import its module in db_registry"


async def test_the_scanner_sees_the_jobs(app_database):
    # Canary: an empty registry would make the test above pass on nothing.
    assert {"heartbeat_check", "revoked_tokens_cleanup", "outbox_cleanup"} <= set(
        job_registry.registered_jobs
    )
