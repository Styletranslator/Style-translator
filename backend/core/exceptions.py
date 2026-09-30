class AppError(Exception):
    """공통 예외 베이스. FastAPI를 모르는 순수 도메인 예외 — main.py의 핸들러가 HTTP로 변환."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str):
        self.message = message
        # 응답에 함께 실을 HTTP 헤더. 대부분의 예외는 비어 있습니다.
        self.headers: dict[str, str] = {}
        super().__init__(message)


class ApiKeyNotConfiguredError(AppError):
    status_code = 500
    code = "API_KEY_NOT_CONFIGURED"


class UnknownStyleError(AppError):
    status_code = 400
    code = "UNKNOWN_STYLE"


class EmptyTextError(AppError):
    status_code = 400
    code = "EMPTY_TEXT"


class TranslationEngineError(AppError):
    status_code = 502
    code = "TRANSLATION_ENGINE_ERROR"


class RateLimitExceededError(AppError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after
        self.headers = {"Retry-After": str(retry_after)}
