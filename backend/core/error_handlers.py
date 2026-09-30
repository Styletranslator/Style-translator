import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.exceptions import AppError

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


async def app_error_handler(_request: Request, exc: AppError):
    if exc.status_code >= 500:
        logger.error("AppError: %s", exc.code, exc_info=exc)
    else:
        logger.warning("AppError: %s - %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message),
        headers=exc.headers,
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = ".".join(str(loc) for loc in first["loc"][1:])
    message = f"{field}: {first['msg']}" if field else first["msg"]
    return JSONResponse(status_code=422, content=_error_body("VALIDATION_ERROR", message))


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("처리되지 않은 예외: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500, content=_error_body("INTERNAL_ERROR", "서버 오류가 발생했습니다.")
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
