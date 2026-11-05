class AppException(Exception):
    def __init__(self, message: str, code: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found", "NOT_FOUND", 404)


class ConflictError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(message, "CONFLICT", 409)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(AppException):
    def __init__(self, message: str = "You don't have access to this") -> None:
        super().__init__(message, "FORBIDDEN", 403)


class PasswordChangeRequiredError(AppException):
    def __init__(self) -> None:
        super().__init__("Set a new password to continue", "PASSWORD_CHANGE_REQUIRED", 403)


class RateLimitedError(AppException):
    def __init__(self) -> None:
        super().__init__("Too many attempts. Try again in a minute.", "RATE_LIMITED", 429)
