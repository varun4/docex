from app.enums import ErrorCode


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str = "",
        detail: str = "",
        status_code: int = 400,
    ):
        self.code = code
        self.message = message or str(code.value)
        self.detail = detail
        self.status_code = status_code
        super().__init__(self.message)
