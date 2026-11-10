from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# The library defaults (Argon2id, RFC 9106 low-memory profile). Not pinned here on purpose:
# a release that raises them is picked up, and `needs_rehash` upgrades each stored hash
# the next time its owner logs in.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    # A wrong password, and also a stored value that is not an Argon2 hash at all: both
    # are a failed login, not an error of the request.
    except VerificationError, InvalidHashError:
        return False


def needs_rehash(hashed: str) -> bool:
    """Whether the hash was made with parameters older than the current ones."""
    return _hasher.check_needs_rehash(hashed)
