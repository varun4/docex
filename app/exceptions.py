"""Custom exception hierarchy using ErrorCode for structured error responses."""

from app.enums import ErrorCode


class AppError(Exception):
    """Application-level exception with an ErrorCode, message, detail, and HTTP status code."""
    def __init__(
        self,
        code: ErrorCode,
        message: str = "",
        detail: str = "",
        status_code: int = 400,
    ):
        """Initialize the error.

        Args:
            code: The ErrorCode enum value.
            message: Human-readable error message.
            detail: Additional context or debug information.
            status_code: HTTP status code for the response.
        """
        self.code = code
        self.message = message or str(code.value)
        self.detail = detail
        self.status_code = status_code
        super().__init__(self.message)
