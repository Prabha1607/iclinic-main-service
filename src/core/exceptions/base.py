"""Base exception classes for the iClinic main service.

Defines a hierarchy of application-specific exceptions that can be caught
by the global exception handler to return appropriate HTTP error responses.
"""


class AppError(Exception):
    """Base application exception carrying an HTTP status code.

    Args:
        message: Human-readable error message.
        status_code: HTTP status code to return (default 400).
    """

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ValidationError(AppError):
    """Raised when incoming data fails validation checks (HTTP 400)."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)
