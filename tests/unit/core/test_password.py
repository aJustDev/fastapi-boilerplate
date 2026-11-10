from argon2 import PasswordHasher

from app.core.security.password import hash_password, needs_rehash, verify_password


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

    def test_hash_is_argon2id(self):
        assert hash_password("test").startswith("$argon2id$")

    def test_a_stored_value_that_is_not_a_hash_is_a_failed_login(self):
        # A corrupted or imported row must not turn a login into a 500.
        assert not verify_password("anything", "not-a-hash")
        assert not verify_password("anything", "")


class TestRehash:
    def test_a_fresh_hash_does_not_need_it(self):
        assert not needs_rehash(hash_password("pw"))

    def test_a_hash_with_weaker_parameters_needs_it(self):
        weaker = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("pw")
        assert verify_password("pw", weaker)
        assert needs_rehash(weaker)
