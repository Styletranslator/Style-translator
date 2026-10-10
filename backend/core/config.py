import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    MODEL_NAME: str = "gemini-3.5-flash"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # 번역 캐시와 rate limiter가 함께 쓰는 Redis (clients/redis_client.py).
    # 비어 있으면 둘 다 꺼진 채로 동작합니다.
    REDIS_URL: str = os.environ.get("REDIS_URL", "")
    # Redis 연결/명령 타임아웃. 평소 응답은 1ms 미만이라 넉넉하고, 장애 시 요청이 이만큼만 늦어집니다.
    REDIS_TIMEOUT_SECONDS: float = float(os.environ.get("REDIS_TIMEOUT_SECONDS", "0.5"))

    # 번역 캐시 (clients/cache.py).
    CACHE_ENABLED: bool = os.environ.get("CACHE_ENABLED", "true").lower() != "false"
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))

    # 요청 횟수 제한. 카운터도 REDIS_URL의 Redis에 두므로, 비어 있으면 제한 없이 동작합니다
    # (clients/rate_limiter.py). 클라이언트(IP)마다 WINDOW_SECONDS 동안 REQUESTS회까지 허용.
    RATE_LIMIT_ENABLED: bool = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "false"
    RATE_LIMIT_REQUESTS: int = int(os.environ.get("RATE_LIMIT_REQUESTS", "10"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # 장문 번역의 용어집 선추출 타임아웃. 모든 청크가 추출을 기다리므로 번역 호출보다 짧게 잡고,
    # 넘기면 용어집 없이 번역합니다 (services/translate.py).
    GLOSSARY_TIMEOUT_SECONDS: float = float(os.environ.get("GLOSSARY_TIMEOUT_SECONDS", "8"))


settings = Settings()
