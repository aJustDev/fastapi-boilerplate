from app.auth.models.user import UserORM


class TestAcceptsSession:
    def test_a_token_of_the_current_version_is_accepted(self):
        assert UserORM(session_version=3).accepts_session(3)

    def test_a_token_of_an_earlier_version_is_rejected(self):
        # The version was bumped after the token was issued: its session has ended.
        assert not UserORM(session_version=3).accepts_session(2)

    def test_a_token_of_a_later_version_is_rejected(self):
        assert not UserORM(session_version=3).accepts_session(4)

    def test_only_an_integer_can_match(self):
        # The claim comes from a token: "3", 3.0 or True are not the version 3.
        user = UserORM(session_version=1)
        assert not user.accepts_session("1")
        assert not user.accepts_session(1.0)
        assert not user.accepts_session(True)
        assert not user.accepts_session(None)
