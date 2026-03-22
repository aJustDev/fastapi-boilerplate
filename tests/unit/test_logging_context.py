from app.core.logging.context import get_request_id, request_id_var


class TestRequestIdContext:
    def test_default_is_empty_string(self):
        assert get_request_id() == ""

    def test_set_and_get(self):
        token = request_id_var.set("req-123")
        try:
            assert get_request_id() == "req-123"
        finally:
            request_id_var.reset(token)

    def test_reset_restores_default(self):
        token = request_id_var.set("req-456")
        request_id_var.reset(token)
        assert get_request_id() == ""
