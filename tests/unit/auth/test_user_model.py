from datetime import UTC, datetime

from app.models.auth.user import UserORM


class TestAcceptsTokenIssuedAt:
    cut_off = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def test_no_cut_off_accepts_everything(self):
        assert UserORM(tokens_valid_after=None).accepts_token_issued_at(0)

    def test_token_issued_before_the_cut_off_is_rejected(self):
        user = UserORM(tokens_valid_after=self.cut_off)
        assert not user.accepts_token_issued_at(self.cut_off.timestamp() - 1)

    def test_token_issued_in_the_same_second_is_accepted(self):
        # `iat` has second precision: a login right after the invalidation must work.
        user = UserORM(tokens_valid_after=self.cut_off)
        assert user.accepts_token_issued_at(self.cut_off.timestamp())
