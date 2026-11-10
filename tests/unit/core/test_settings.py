import pytest

from app.core.config import Settings


def test_suite_reads_no_env_file():
    # tests/conftest.py sets SETTINGS_ENV_FILE="": a developer's .env.local must not
    # change what the suite sees.
    assert Settings.model_config["env_file"] is None


def test_app_version_comes_from_the_package():
    from importlib.metadata import version

    assert version("app") == Settings().APP_VERSION


class TestSecretKey:
    def test_placeholder_is_rejected_outside_local(self):
        with pytest.raises(ValueError, match="changed from default"):
            Settings(ENVIRONMENT="prod")

    def test_short_key_is_rejected_outside_local(self):
        with pytest.raises(ValueError, match="at least 32 bytes"):
            Settings(ENVIRONMENT="prod", SECRET_KEY="x" * 31)

    def test_long_random_key_is_accepted(self):
        assert Settings(ENVIRONMENT="prod", SECRET_KEY="x" * 32).SECRET_KEY == "x" * 32
