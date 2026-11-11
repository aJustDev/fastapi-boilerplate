import logging

from app.core.logging.context import request_id_var
from app.core.logging.filters import (
    IgnoreHealthcheckFilter,
    IgnoreMetricsFilter,
    IgnoreOptionsFilter,
    LayerModuleFilter,
    RequestIdFilter,
)


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
        record = self._make_record("app.orders.api.router")

        result = f.filter(record)

        assert result is True
        assert record.layer_name == "Router"

    def test_services_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.auth.services.auth")

        f.filter(record)

        assert record.layer_name == "Service"

    def test_repos_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.orders.repos.order")

        f.filter(record)

        assert record.layer_name == "Repo"

    def test_core_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.core.startup")

        f.filter(record)

        assert record.layer_name == "Core"

    def test_use_cases_layer(self):
        f = LayerModuleFilter()
        record = self._make_record("app.auth.use_cases.login")

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
        record = self._make_record("app.orders.api.router")

        f.filter(record)

        assert hasattr(record, "colored_layer")
        assert "Router" in record.colored_layer

    def test_colored_module_set(self):
        f = LayerModuleFilter()
        record = self._make_record("app.auth.services.auth")

        f.filter(record)

        assert hasattr(record, "colored_module")
        assert "Auth" in record.colored_module

    def test_module_name_is_last_segment(self):
        f = LayerModuleFilter()
        record = self._make_record("app.orders.repos.order")

        f.filter(record)

        assert record.module_name == "Order"

    def test_module_name_title_cased(self):
        f = LayerModuleFilter()
        record = self._make_record("app.core.startup")

        f.filter(record)

        assert record.module_name == "Startup"

    def test_module_underscores_to_title(self):
        f = LayerModuleFilter()
        record = self._make_record("app.auth.use_cases.refresh_token")

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
        record = self._make_record("app.auth.services.auth")

        f.filter(record)

        assert "\033[36m" in record.colored_module  # cyan


def _access(method: str, full_path: str, status: int = 200) -> logging.LogRecord:
    """A record shaped like the ones uvicorn's access logger emits."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:5000", method, full_path, "1.1", status),
        exc_info=None,
    )


def _plain(msg: str, name: str = "app.orders.api.router") -> logging.LogRecord:
    return logging.LogRecord(
        name=name, level=logging.INFO, pathname="", lineno=0, msg=msg, args=(), exc_info=None
    )


class TestIgnoreOptionsFilter:
    def test_options_request_is_dropped(self):
        assert IgnoreOptionsFilter().filter(_access("OPTIONS", "/v1/orders")) is False

    def test_other_methods_are_kept(self):
        assert IgnoreOptionsFilter().filter(_access("GET", "/v1/orders")) is True
        assert IgnoreOptionsFilter().filter(_access("POST", "/v1/orders", 201)) is True

    def test_only_access_records_are_judged(self):
        # The filter sits on the console handler of every logger: an application line that
        # happens to quote a request must never be dropped.
        assert IgnoreOptionsFilter().filter(_plain('client sent "OPTIONS /v1/orders"')) is True


class TestNoiseFiltersLookAtThePathOnly:
    def test_liveness_probe_is_dropped(self):
        assert IgnoreHealthcheckFilter().filter(_access("GET", "/v1/health/liveness")) is False

    def test_metrics_scrape_is_dropped(self):
        assert IgnoreMetricsFilter().filter(_access("GET", "/v1/metrics")) is False

    def test_a_query_string_cannot_hide_a_request(self):
        # The access line of a request is its audit trail (source address, status). Anything
        # a client controls must not be able to remove it.
        login = _access("POST", "/v1/auth/login?/v1/metrics", 401)
        delete = _access("DELETE", "/v1/orders/3?x=/v1/health/liveness", 204)

        for f in (IgnoreHealthcheckFilter(), IgnoreMetricsFilter()):
            assert f.filter(login) is True
            assert f.filter(delete) is True

    def test_a_longer_path_is_not_the_probe(self):
        assert IgnoreMetricsFilter().filter(_access("GET", "/v1/metrics/extra")) is True
        assert IgnoreHealthcheckFilter().filter(_access("GET", "/x/v1/health/liveness")) is True


class TestRequestIdFilter:
    def _make_record(self, msg: str = "test") -> logging.LogRecord:
        return logging.LogRecord(
            name="app.orders.api.router",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_injects_request_id_from_context(self):
        token = request_id_var.set("abc123")
        try:
            f = RequestIdFilter()
            record = self._make_record()
            f.filter(record)
            assert record.request_id == "abc123"
        finally:
            request_id_var.reset(token)

    def test_empty_when_no_context(self):
        f = RequestIdFilter()
        record = self._make_record()
        f.filter(record)
        assert record.request_id == ""

    def test_the_text_formats_print_the_id_only_during_a_request(self):
        record = self._make_record()
        RequestIdFilter().filter(record)
        assert record.request_tag == ""

        token = request_id_var.set("abc123")
        try:
            RequestIdFilter().filter(record)
        finally:
            request_id_var.reset(token)
        assert record.request_tag == "[abc123] "

    def test_always_returns_true(self):
        f = RequestIdFilter()
        record = self._make_record()
        assert f.filter(record) is True

    def test_router_module_is_named_after_its_context(self):
        f = LayerModuleFilter()
        record = self._make_record("app.orders.api.router")

        f.filter(record)

        assert record.layer_name == "Router"
        assert record.module_name == "Orders"
