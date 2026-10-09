"""POST /translate — rate limiting (429), Redis 카운터, 장애 처리.

실제 Redis 서버는 띄우지 않습니다. 엔드포인트는 conftest의 FakeRateLimiter를,
RedisRateLimiter 자체는 아래 FakeRedis/BrokenRedis를 주입해 검증합니다.
"""

import pytest

from clients.rate_limiter import (
    KEY_PREFIX,
    NullRateLimiter,
    RedisRateLimiter,
    build_rate_limiter,
)
from clients.redis_client import create_redis_client
from conftest import error_code, error_message
from core.config import settings


def payload(**overrides) -> dict:
    body = {"text": "이거 언제까지 가능해?", "target_lang": "한국어", "style": "general"}
    body.update(overrides)
    return body


# ---------- 엔드포인트 ----------


def test_translate_allows_requests_up_to_the_limit(client, fake_rate_limiter):
    fake_rate_limiter.limit = 3

    for _ in range(3):
        assert client.post("/translate", json=payload()).status_code == 200


def test_translate_returns_429_once_limit_exceeded(client, fake_rate_limiter):
    fake_rate_limiter.limit = 3
    for _ in range(3):
        client.post("/translate", json=payload())

    res = client.post("/translate", json=payload())

    assert res.status_code == 429
    assert error_code(res) == "RATE_LIMIT_EXCEEDED"


def test_429_tells_client_when_to_retry(client, fake_rate_limiter):
    """Retry-After 헤더와 메시지 양쪽에 남은 시간이 들어갑니다.

    프론트엔드는 에러 메시지를 그대로 보여주므로 메시지에도 초가 있어야 사용자가 알 수 있습니다.
    """
    fake_rate_limiter.limit = 0
    fake_rate_limiter.retry_after = 17

    res = client.post("/translate", json=payload())

    assert res.headers["Retry-After"] == "17"
    assert "17초" in error_message(res)


def test_blocked_request_does_not_call_gemini(client, fake_client, fake_rate_limiter):
    """이 기능의 목적 — 한도를 넘긴 요청은 Gemini까지 가지 않아야 합니다."""
    fake_rate_limiter.limit = 0

    client.post("/translate", json=payload())

    assert fake_client.calls == []


def test_cache_hits_count_toward_the_limit(client, fake_client, fake_rate_limiter):
    """같은 문장을 반복해도 횟수는 쌓입니다 — 제한이 캐시 조회보다 앞에서 걸리기 때문."""
    fake_rate_limiter.limit = 2
    client.post("/translate", json=payload())
    client.post("/translate", json=payload())

    res = client.post("/translate", json=payload())

    assert res.status_code == 429
    assert len(fake_client.calls) == 1


def test_limit_is_counted_per_client_ip(client, fake_rate_limiter):
    client.post("/translate", json=payload())

    # TestClient가 보내는 요청의 클라이언트 주소는 "testclient"입니다.
    assert fake_rate_limiter.hits == ["testclient"]


def test_health_and_styles_are_not_rate_limited(client, fake_rate_limiter):
    fake_rate_limiter.limit = 0

    assert client.get("/health").status_code == 200
    assert client.get("/styles").status_code == 200
    assert fake_rate_limiter.hits == []


# ---------- RedisRateLimiter ----------


class FakeRedis:
    """redis.asyncio 클라이언트 대역. pipeline()의 INCR / EXPIRE만 흉내 냅니다.

    redis.asyncio와 같이 pipeline()/incr()/expire()는 동기(명령을 쌓기만 함)이고 execute()만 async입니다.
    """

    def __init__(self):
        self.counts: dict = {}
        self.ttls: dict = {}

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._ops: list = []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))

    async def execute(self):
        results = []
        for op, key, *args in self._ops:
            if op == "incr":
                self._redis.counts[key] = self._redis.counts.get(key, 0) + 1
                results.append(self._redis.counts[key])
            else:
                self._redis.ttls[key] = args[0]
                results.append(True)
        return results


class BrokenRedis:
    """모든 명령이 실패하는 Redis — 연결 끊김/타임아웃 상황."""

    def pipeline(self):
        return self

    def incr(self, key):
        pass

    def expire(self, key, seconds):
        pass

    async def execute(self):
        raise ConnectionError("redis 연결 실패")


class Clock:
    """테스트에서 시간을 직접 옮기기 위한 시계."""

    def __init__(self, now: float):
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_limiter(limit=3, window=60, now=1000.0, redis=None):
    clock = Clock(now)
    limiter = RedisRateLimiter(redis or FakeRedis(), limit=limit, window_seconds=window, clock=clock)
    return limiter, clock


@pytest.mark.anyio
async def test_redis_limiter_allows_up_to_limit_then_blocks():
    limiter, _ = make_limiter(limit=3)

    assert [await limiter.hit("1.2.3.4") for _ in range(3)] == [None, None, None]
    assert await limiter.hit("1.2.3.4") is not None


@pytest.mark.anyio
async def test_redis_limiter_returns_seconds_until_window_ends():
    # 윈도우 60초, 현재 1000초 → 이번 윈도우는 960~1020초. 남은 시간 20초.
    limiter, _ = make_limiter(limit=0, window=60, now=1000.0)

    assert await limiter.hit("1.2.3.4") == 20


@pytest.mark.anyio
async def test_redis_limiter_retry_after_is_at_least_one_second():
    """윈도우 끝 직전이어도 0초가 아니라 최소 1초를 돌려줘야 합니다 (Retry-After: 0은 무의미)."""
    limiter, _ = make_limiter(limit=0, window=60, now=1019.9)

    assert await limiter.hit("1.2.3.4") == 1


@pytest.mark.anyio
async def test_redis_limiter_resets_in_next_window():
    limiter, clock = make_limiter(limit=1, now=1000.0)
    await limiter.hit("1.2.3.4")
    assert await limiter.hit("1.2.3.4") is not None

    clock.now = 1020.0  # 다음 윈도우 시작

    assert await limiter.hit("1.2.3.4") is None


@pytest.mark.anyio
async def test_redis_limiter_counts_each_client_separately():
    limiter, _ = make_limiter(limit=1)
    await limiter.hit("1.1.1.1")

    assert await limiter.hit("2.2.2.2") is None


@pytest.mark.anyio
async def test_redis_limiter_sets_expiry_so_keys_do_not_pile_up():
    """윈도우마다 새 key를 쓰므로 만료가 없으면 Redis에 key가 계속 쌓입니다."""
    fake_redis = FakeRedis()
    limiter, _ = make_limiter(window=60, redis=fake_redis)

    await limiter.hit("1.2.3.4")

    [(key, ttl)] = fake_redis.ttls.items()
    assert key.startswith(f"{KEY_PREFIX}:1.2.3.4:")
    assert ttl == 60


@pytest.mark.anyio
async def test_redis_failure_lets_request_through():
    """Redis가 죽어도 요청을 막으면 안 됩니다 (fail-open)."""
    limiter, _ = make_limiter(limit=0, redis=BrokenRedis())

    assert await limiter.hit("1.2.3.4") is None


@pytest.mark.anyio
async def test_null_rate_limiter_never_blocks():
    limiter = NullRateLimiter()

    assert [await limiter.hit("1.2.3.4") for _ in range(1000)] == [None] * 1000


# ---------- rate limiter 구성 ----------


def test_build_rate_limiter_returns_null_without_redis_url(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")

    assert isinstance(build_rate_limiter(create_redis_client()), NullRateLimiter)


def test_build_rate_limiter_returns_null_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    assert isinstance(build_rate_limiter(create_redis_client()), NullRateLimiter)


def test_build_rate_limiter_returns_redis_limiter_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    # from_url()은 지연 연결이라 Redis가 떠 있지 않아도 이 호출은 성공해야 합니다.
    assert isinstance(build_rate_limiter(create_redis_client()), RedisRateLimiter)
