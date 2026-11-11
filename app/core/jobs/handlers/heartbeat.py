from app.core.jobs.registry import job_registry


@job_registry.register("heartbeat_check")
async def heartbeat_check() -> None:
    """Example job: it does nothing, and the line of its run says which worker took it.

    The job worker logs every run at DEBUG with the worker that claimed it (`job.worker`
    in JSON), so with several instances it shows that each run went to only one.
    """
