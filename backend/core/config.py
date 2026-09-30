import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    MODEL_NAME: str = "gemini-3.5-flash"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # 번역 캐시가 쓰는 Redis (clients/redis_client.py). 비어 있으면 캐시 없이 동작합니다.
    REDIS_URL: str = os.environ.get("REDIS_URL", "")
    # Redis 연결/명령 타임아웃. 평소 응답은 1ms 미만이라 넉넉하고, 장애 시 요청이 이만큼만 늦어집니다.
    REDIS_TIMEOUT_SECONDS: float = 0.5

    # 번역 캐시 (clients/cache.py).
    CACHE_ENABLED: bool = os.environ.get("CACHE_ENABLED", "true").lower() != "false"
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))


settings = Settings()
