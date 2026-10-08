import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from clients.redis_client import redis_client
from core.config import settings
from core.error_handlers import register_exception_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # 캐시와 rate limiter가 함께 쓰는 Redis 연결 풀을 서버 종료 시 닫습니다.
    if redis_client is not None:
        await redis_client.aclose()


app = FastAPI(title="스타일 번역 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
register_exception_handlers(app)
