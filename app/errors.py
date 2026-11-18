class AppError(Exception):
    """Domain error rendered as {"error": {"code", "message"}} with an HTTP status."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict | None = None):
        """Store the HTTP status, machine-readable code, message and optional response headers."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def not_found(message: str = "Link not found") -> AppError:
    """Build a 404 not_found error."""
    return AppError(404, "not_found", message)


def conflict(message: str) -> AppError:
    """Build a 409 conflict error."""
    return AppError(409, "conflict", message)


def bad_request(message: str, code: str = "invalid_request") -> AppError:
    """Build a 400 error with the given code (default invalid_request)."""
    return AppError(400, code, message)
