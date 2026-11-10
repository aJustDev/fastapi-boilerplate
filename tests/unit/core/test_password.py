from app.core.security.password import hash_password, verify_password


class TestPassword:
    def test_hash_and_verify(self):
        hashed = hash_password("my_secret_password")
        assert verify_password("my_secret_password", hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_hash_is_different_each_time(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_hash_starts_with_argon2(self):
        hashed = hash_password("test")
        assert hashed.startswith("$argon2")
