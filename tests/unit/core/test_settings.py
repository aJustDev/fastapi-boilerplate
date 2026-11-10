import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_suite_reads_no_env_file():
    # tests/conftest.py sets SETTINGS_ENV_FILE="": a developer's .env.local must not
    # change what the suite sees.
    assert Settings.model_config["env_file"] is None


def test_app_version_comes_from_the_package():
    from importlib.metadata import version

    assert version("app") == Settings().APP_VERSION


class TestEnvironment:
    def test_environment_has_no_default(self, monkeypatch):
        # Falling back to "local" would switch every production validator off, placeholder
        # SECRET_KEY included, the day a deployment forgets the variable.
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(ValidationError, match="ENVIRONMENT"):
            Settings()

    def test_placeholder_key_needs_an_explicit_local(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "local")
        assert Settings().SECRET_KEY.startswith("change-me")


class TestSecretKey:
    def test_placeholder_is_rejected_outside_local(self):
        with pytest.raises(ValueError, match="changed from default"):
            Settings(ENVIRONMENT="prod")

    def test_short_key_is_rejected_outside_local(self):
        with pytest.raises(ValueError, match="at least 32 bytes"):
            Settings(ENVIRONMENT="prod", SECRET_KEY="x" * 31)

    def test_long_random_key_is_accepted(self):
        s = Settings(ENVIRONMENT="prod", SECRET_KEY="x" * 32, ALLOWED_HOSTS=["api.example.com"])
        assert s.SECRET_KEY == "x" * 32


class TestNetworkExposure:
    prod = {"ENVIRONMENT": "prod", "SECRET_KEY": "x" * 32}

    def test_wildcard_hosts_are_rejected_outside_local(self):
        with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
            Settings(**self.prod, ALLOWED_HOSTS=["*"])

    def test_wildcard_origins_are_rejected_outside_local(self):
        with pytest.raises(ValueError, match="ALLOWED_ORIGINS"):
            Settings(**self.prod, ALLOWED_HOSTS=["api.example.com"], ALLOWED_ORIGINS=["*"])

    def test_trusting_every_proxy_is_rejected_outside_local(self):
        with pytest.raises(ValueError, match="FORWARDED_ALLOW_IPS"):
            Settings(**self.prod, ALLOWED_HOSTS=["api.example.com"], FORWARDED_ALLOW_IPS="*")

    def test_explicit_values_are_accepted(self):
        s = Settings(
            **self.prod,
            ALLOWED_HOSTS=["api.example.com"],
            ALLOWED_ORIGINS=["https://app.example.com"],
            FORWARDED_ALLOW_IPS="10.0.0.0/8",
        )
        assert s.ALLOWED_HOSTS == ["api.example.com"]

    def test_local_keeps_the_permissive_defaults(self):
        assert Settings(ENVIRONMENT="local").ALLOWED_HOSTS == ["*"]
