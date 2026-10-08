"""공용 Redis 클라이언트.

번역 캐시(clients/cache.py)와 rate limiter(clients/rate_limiter.py)가 같은 Redis를 쓰므로
연결 풀과 타임아웃 설정을 여기 한 곳에서 만듭니다. 두 모듈은 key prefix로 공간을 나눕니다.
"""

import logging

from core.config import settings

logger = logging.getLogger(__name__)


def create_redis_client():
    """설정에 맞는 Redis 클라이언트를 만듭니다. 쓸 수 없는 상황이면 None을 돌려줍니다."""
    if not settings.REDIS_URL:
        return None

    try:
        import redis.asyncio as redis
    except ImportError:
        logger.warning("redis 패키지가 설치되지 않아 Redis를 사용하지 않습니다")
        return None

    # from_url()은 지연 연결이라 Redis가 떠 있지 않아도 import와 앱 기동은 성공합니다.
    #
    # 비동기 클라이언트(redis.asyncio)입니다. 동기 클라이언트를 async 라우트에서 부르면
    # 명령이 끝날 때까지 이벤트 루프가 멈춰 다른 요청도 전부 멈춥니다.
    #
    # 타임아웃을 반드시 겁니다. redis-py 기본값은 무한 대기라, Redis가 응답하지 않으면
    # (네트워크 단절, failover 등) 모든 /translate 요청이 Redis를 기다리며 끝나지 않습니다.
    # 캐시와 rate limiter는 실패해도 통과하도록 되어 있으니, 빨리 포기하는 편이 낫습니다.
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
    )


# 모듈 싱글톤. REDIS_URL이 없으면 None이고, 캐시와 rate limiter는 각자 Null 구현으로 내려갑니다.
redis_client = create_redis_client()
