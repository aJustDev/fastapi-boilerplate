from typing import ClassVar


class DomainException(Exception):
    """Base exception for all domain errors.

    `code` is the stable identifier of the error that travels in the response
    (`{"detail": ..., "code": ...}`): clients branch on it. `message` is free text and
    may change; the code may not.
    """

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str = "Internal server error"):
        self.message = message
        super().__init__(message)


class UseCaseException(DomainException):
    """Base for business logic errors."""

    status_code = 400
    code = "use_case_error"


class NotFoundError(UseCaseException):
    status_code = 404
    code = "not_found"

    def __init__(self, entity: str, entity_id: int | str | None = None):
        msg = f"{entity} not found" + (f" (ID: {entity_id})" if entity_id is not None else "")
        super().__init__(msg)


class ConflictError(UseCaseException):
    status_code = 409
    code = "conflict"

    def __init__(self, entity: str, detail: str | None = None):
        msg = f"Conflict on {entity}" + (f": {detail}" if detail else "")
        super().__init__(msg)


class BusinessValidationError(UseCaseException):
    status_code = 400
    code = "business_validation"


class InvalidCursorError(UseCaseException):
    """The pagination cursor was not issued by this API, or not for this ordering."""

    status_code = 400
    code = "invalid_cursor"

    def __init__(self) -> None:
        super().__init__("Invalid pagination cursor")


class RepoException(DomainException):
    """Base for data access errors."""

    status_code = 500
    code = "repo_error"


class AuthException(DomainException):
    """Base for authentication/authorization errors."""

    code = "auth_error"
    headers: ClassVar[dict[str, str]] = {}


class AuthenticationError(AuthException):
    status_code = 401
    code = "unauthenticated"
    headers: ClassVar[dict[str, str]] = {"WWW-Authenticate": "Bearer"}

    def __init__(self, message: str = "Invalid or expired credentials"):
        super().__init__(message)


class RefreshTokenReuseError(AuthenticationError):
    """A refresh token that was already rotated came back: it was stolen or leaked.

    Its own code tells the client that every session ended, not just this request.
    """

    code = "refresh_token_reused"

    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__("Refresh token has been revoked")


class AuthorizationError(AuthException):
    status_code = 403
    code = "forbidden"

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message)
