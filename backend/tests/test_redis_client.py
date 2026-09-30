"""공용 Redis 클라이언트 — 생성 조건과 타임아웃 설정.

실제 Redis 서버에는 연결하지 않습니다. from_url()은 지연 연결이라 생성만으로는 네트워크를 타지 않습니다.
"""

from clients.cache import RedisCache, build_cache
from clients.rate_limiter import RedisRateLimiter, build_rate_limiter
from clients.redis_client import create_redis_client
from core.config import settings


def test_no_client_without_redis_url(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")

    assert create_redis_client() is None


def test_client_has_timeouts(monkeypatch):
    """타임아웃이 없으면 Redis가 응답하지 않을 때 요청 스레드가 무한정 묶입니다.

    redis-py 기본값은 무한 대기(None)라 직접 설정하지 않으면 이 테스트가 실패합니다.
    """
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    kwargs = create_redis_client().connection_pool.connection_kwargs

    assert kwargs["socket_connect_timeout"] == settings.REDIS_TIMEOUT_SECONDS
    assert kwargs["socket_timeout"] == settings.REDIS_TIMEOUT_SECONDS


def test_cache_and_rate_limiter_share_one_client(monkeypatch):
    """같은 Redis에 연결 풀을 두 개 만들지 않도록 클라이언트 하나를 나눠 씁니다."""
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    client = create_redis_client()

    cache = build_cache(client)
    limiter = build_rate_limiter(client)

    assert isinstance(cache, RedisCache)
    assert isinstance(limiter, RedisRateLimiter)
    assert cache._client is limiter._client
