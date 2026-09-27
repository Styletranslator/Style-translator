"""번역 결과 캐시.

같은 (text, target_lang, style) 조합에 대한 중복 Gemini 호출을 없애기 위한 계층.
서비스 레이어는 아래 TranslationCache 프로토콜에만 의존하고 Redis를 직접 알지 못합니다.
"""

import hashlib
import json
import logging
from typing import Any, Protocol

from core.config import settings

logger = logging.getLogger(__name__)

# 캐시에 저장하는 값의 형식이 바뀌면 이 버전을 올리고 아래 이력에 한 줄 추가하세요.
# 과거 캐시는 key가 달라져 조회되지 않고, 남은 항목은 TTL로 사라집니다.
#
#   v1 — str        번역 결과 1개
#   v2 — list[str]  서로 다른 번역 후보 3개 (#11)
#
# 현재 형식의 정의처는 models/schemas.py의 TranslateResponse입니다.
# 버전을 올리는 것을 잊어도 services/translate.py가 형식을 검증해 옛 값을 무시합니다.
KEY_PREFIX = "translate:v2"


def build_cache_key(text: str, target_lang: str, style: str) -> str:
    """세 값이 모두 같을 때만 같은 key가 나오도록 만듭니다.

    원문이 최대 2000자라 그대로 key에 쓰지 않고 sha256으로 고정 길이를 만듭니다.
    구분자 없이 이어붙이면 ("ab", "c")와 ("a", "bc")가 같은 key가 되므로 JSON 배열로 직렬화합니다.
    """
    raw = json.dumps([text, target_lang, style], ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}:{digest}"


class TranslationCache(Protocol):
    """캐시 구현이 지켜야 할 최소 계약.

    get()/set()은 어떤 경우에도 예외를 밖으로 던지지 않습니다. 캐시는 성능 장치이므로
    캐시가 죽었을 때 번역이 느려질 수는 있어도 실패해서는 안 됩니다.
    """

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any) -> None: ...


class NullCache:
    """캐시를 쓰지 않는 상태. 항상 miss이므로 매번 Gemini를 호출합니다."""

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any) -> None:
        return None


class RedisCache:
    """Redis 백엔드. 값은 JSON으로 직렬화해 저장합니다.

    JSON을 쓰는 이유는 Redis가 문자열만 담기 때문입니다. 저장하는 값이 나중에
    문자열에서 리스트 등으로 바뀌어도 이 클래스는 그대로 둘 수 있습니다.
    """

    def __init__(self, client, ttl_seconds: int):
        self._client = client
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except Exception:
            # 연결 실패, 타임아웃 등 원인을 가리지 않고 삼킵니다 (위 프로토콜 주석 참고).
            logger.warning("캐시 조회 실패 - 캐시 없이 진행합니다", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("캐시 값 형식이 올바르지 않아 무시합니다: %s", key)
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._client.set(key, json.dumps(value, ensure_ascii=False), ex=self._ttl)
        except Exception:
            logger.warning("캐시 저장 실패 - 무시합니다", exc_info=True)


def build_cache() -> TranslationCache:
    """설정에 맞는 캐시를 만듭니다. 쓸 수 없는 상황이면 NullCache로 조용히 내려갑니다."""
    if not settings.CACHE_ENABLED:
        logger.info("번역 캐시 비활성화됨 (CACHE_ENABLED=false)")
        return NullCache()
    if not settings.REDIS_URL:
        logger.info("REDIS_URL이 없어 번역 캐시를 비활성화합니다")
        return NullCache()

    try:
        import redis
    except ImportError:
        logger.warning("redis 패키지가 설치되지 않아 번역 캐시를 비활성화합니다")
        return NullCache()

    # from_url()은 지연 연결이라 여기서 네트워크를 타지 않습니다.
    # 따라서 Redis가 떠 있지 않아도 import와 앱 기동은 성공합니다.
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return RedisCache(client, settings.CACHE_TTL_SECONDS)


# clients/gemini.py의 gemini_client와 같은 모듈 싱글톤 패턴.
translation_cache = build_cache()
