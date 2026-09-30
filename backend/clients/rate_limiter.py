"""요청 횟수 제한 (rate limiting).

클라이언트마다 고정 윈도우(기본 60초) 안의 요청 수를 셉니다. 카운터를 Redis에 두므로
서버 프로세스/인스턴스를 여러 개로 늘려도 한도를 공유합니다. 라우트는 아래 RateLimiter
프로토콜에만 의존하고 Redis를 직접 알지 못합니다 (clients/cache.py와 같은 구조).
"""

import logging
import math
import time
from typing import Protocol

from clients.redis_client import redis_client
from core.config import settings

logger = logging.getLogger(__name__)

# 번역 캐시(translate:v2:...)와 같은 Redis를 쓰므로 key 공간을 나눕니다.
KEY_PREFIX = "ratelimit"


class RateLimiter(Protocol):
    """rate limiter 구현이 지켜야 할 최소 계약.

    hit()은 어떤 경우에도 예외를 밖으로 던지지 않습니다. 카운터 저장소가 죽었을 때
    요청을 막으면 Redis 장애가 곧 서비스 장애가 되므로, 제한 없이 통과시킵니다 (fail-open).
    """

    def hit(self, client_id: str) -> int | None:
        """요청 1회를 기록합니다. 허용이면 None, 한도 초과면 다시 시도할 수 있을 때까지 남은 초."""
        ...


class NullRateLimiter:
    """제한을 두지 않는 상태. 모든 요청을 허용합니다."""

    def hit(self, client_id: str) -> int | None:
        return None


class RedisRateLimiter:
    """Redis 고정 윈도우 카운터.

    key에 윈도우 번호를 넣어 윈도우마다 새 카운터를 씁니다. 지난 윈도우의 key는 EXPIRE로
    사라지므로 따로 정리할 필요가 없습니다. INCR와 EXPIRE는 MULTI/EXEC 파이프라인으로
    함께 보내, 중간에 끊겨 만료 시간 없는 key가 남는 일을 막습니다.
    """

    def __init__(self, client, limit: int, window_seconds: int, clock=time.time):
        self._client = client
        self._limit = limit
        self._window = window_seconds
        # 테스트에서 시간을 옮길 수 있도록 주입받습니다.
        self._clock = clock

    def hit(self, client_id: str) -> int | None:
        now = self._clock()
        window_index = int(now // self._window)
        key = f"{KEY_PREFIX}:{client_id}:{window_index}"
        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, self._window)
            count, _ = pipe.execute()
        except Exception:
            # 연결 실패, 타임아웃 등 원인을 가리지 않고 통과시킵니다 (위 프로토콜 주석 참고).
            logger.warning("rate limit 카운터 조회 실패 - 제한 없이 진행합니다", exc_info=True)
            return None

        if count <= self._limit:
            return None
        window_end = (window_index + 1) * self._window
        return max(1, math.ceil(window_end - now))


def build_rate_limiter(client) -> RateLimiter:
    """설정에 맞는 rate limiter를 만듭니다. 쓸 수 없는 상황이면 NullRateLimiter로 조용히 내려갑니다.

    client는 clients/redis_client.py가 만든 공용 Redis 클라이언트 (없으면 None).
    """
    if not settings.RATE_LIMIT_ENABLED:
        logger.info("rate limiting 비활성화됨 (RATE_LIMIT_ENABLED=false)")
        return NullRateLimiter()
    if client is None:
        logger.info("Redis를 쓸 수 없어 rate limiting을 비활성화합니다 (REDIS_URL 확인)")
        return NullRateLimiter()
    return RedisRateLimiter(client, settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS)


# clients/cache.py의 translation_cache와 같은 모듈 싱글톤 패턴.
rate_limiter = build_rate_limiter(redis_client)
