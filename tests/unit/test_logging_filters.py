import logging

from app.core.logging.filters import IgnoreOptionsFilter, LayerModuleFilter


class TestLayerModuleFilter:
    def _make_record(self, name: str, msg: str = "test") -> logging.LogRecord:
        return logging.LogRecord(
            name=name,
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_api_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.api.v1.items")

        result = f.filter(record)

        assert result is True
        assert record.layer_name == "Router"

    def test_services_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.services.items")

        f.filter(record)

        assert record.layer_name == "Service"

    def test_repos_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.repos.items.item")

        f.filter(record)

        assert record.layer_name == "Repo"

    def test_core_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.core.startup")

        f.filter(record)

        assert record.layer_name == "Core"

    def test_use_cases_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.use_cases.auth.login")

        f.filter(record)

        assert record.layer_name == "UseCase"

    def test_deps_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.deps.auth")

        f.filter(record)

        assert record.layer_name == "Deps"

    def test_unknown_layer_defaults_to_app(self):
        f = LayerModuleFilter()
        record = self._make_record("some.other.module")

        f.filter(record)

        assert record.layer_name == "App"

    def test_filter_always_returns_true(self):
        f = LayerModuleFilter()
        record = self._make_record("anything")

        assert f.filter(record) is True

    def test_colored_layer_set(self):
        f = LayerModuleFilter()
        record = self._make_record("app.api.v1.items")

        f.filter(record)

        assert hasattr(record, "colored_layer")
        assert "Router" in record.colored_layer

    def test_colored_module_set(self):
        f = LayerModuleFilter()
        record = self._make_record("app.services.items")

        f.filter(record)

        assert hasattr(record, "colored_module")
        assert "Items" in record.colored_module

    def test_module_name_is_last_segment(self):
        f = LayerModuleFilter()
        record = self._make_record("app.repos.items.item")

        f.filter(record)

        assert record.module_name == "Item"

    def test_module_name_title_cased(self):
        f = LayerModuleFilter()
        record = self._make_record("app.core.startup")

        f.filter(record)

        assert record.module_name == "Startup"

    def test_module_underscores_to_title(self):
        f = LayerModuleFilter()
        record = self._make_record("app.use_cases.auth.refresh_token")

        f.filter(record)

        assert record.module_name == "Refresh Token"

    def test_non_app_logger_extracts_last_segment(self):
        f = LayerModuleFilter()
        record = self._make_record("uvicorn.access")

        f.filter(record)

        assert record.layer_name == "App"
        assert record.module_name == "Access"

    def test_module_color_is_cyan(self):
        f = LayerModuleFilter()
        record = self._make_record("app.services.auth")

        f.filter(record)

        assert "\033[36m" in record.colored_module  # cyan


class TestIgnoreOptionsFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_options_request_returns_false(self):
        f = IgnoreOptionsFilter()
        record = self._make_record('"OPTIONS /api/v1/items HTTP/1.1" 200')

        assert f.filter(record) is False

    def test_get_request_returns_true(self):
        f = IgnoreOptionsFilter()
        record = self._make_record('"GET /api/v1/items HTTP/1.1" 200')

        assert f.filter(record) is True

    def test_post_request_returns_true(self):
        f = IgnoreOptionsFilter()
        record = self._make_record('"POST /api/v1/items HTTP/1.1" 201')

        assert f.filter(record) is True

    def test_plain_message_returns_true(self):
        f = IgnoreOptionsFilter()
        record = self._make_record("Application started")

        assert f.filter(record) is True
