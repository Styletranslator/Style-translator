import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    MODEL_NAME: str = "gemini-3.5-flash"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # 번역 캐시. REDIS_URL이 비어 있으면 캐시 없이 동작합니다 (clients/cache.py).
    REDIS_URL: str = os.environ.get("REDIS_URL", "")
    CACHE_ENABLED: bool = os.environ.get("CACHE_ENABLED", "true").lower() != "false"
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))


settings = Settings()
