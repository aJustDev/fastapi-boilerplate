from app.core.jobs.registry import JobRegistry


class TestJobRegistry:
    def test_register_and_get(self):
        registry = JobRegistry()

        @registry.register("my_job")
        async def my_handler() -> None:
            pass

        assert registry.get("my_job") is my_handler

    def test_get_unknown_returns_none(self):
        registry = JobRegistry()
        assert registry.get("nonexistent") is None

    def test_registered_jobs(self):
        registry = JobRegistry()

        @registry.register("job_a")
        async def handler_a() -> None:
            pass

        @registry.register("job_b")
        async def handler_b() -> None:
            pass

        assert sorted(registry.registered_jobs) == ["job_a", "job_b"]

    def test_register_overwrites_existing(self):
        registry = JobRegistry()

        @registry.register("my_job")
        async def first() -> None:
            pass

        @registry.register("my_job")
        async def second() -> None:
            pass

        assert registry.get("my_job") is second
