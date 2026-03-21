class DomainException(Exception):
    """Base exception for all domain errors."""

    status_code: int = 500

    def __init__(self, message: str = "Internal server error"):
        self.message = message
        super().__init__(message)


class UseCaseException(DomainException):
    """Base for business logic errors."""

    status_code = 400


class NotFoundError(UseCaseException):
    status_code = 404

    def __init__(self, entity: str, entity_id: int | str | None = None):
        msg = f"{entity} not found" + (f" (ID: {entity_id})" if entity_id is not None else "")
        super().__init__(msg)


class ConflictError(UseCaseException):
    status_code = 409

    def __init__(self, entity: str, detail: str | None = None):
        msg = f"Conflict on {entity}" + (f": {detail}" if detail else "")
        super().__init__(msg)


class BusinessValidationError(UseCaseException):
    status_code = 400


class RepoException(DomainException):
    """Base for data access errors."""

    status_code = 500


class AuthException(DomainException):
    """Base for authentication/authorization errors."""

    headers: dict[str, str] = {}


class AuthenticationError(AuthException):
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}

    def __init__(self, message: str = "Invalid or expired credentials"):
        super().__init__(message)


class AuthorizationError(AuthException):
    status_code = 403

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message)
