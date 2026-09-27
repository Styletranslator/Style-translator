"""번역 결과 캐싱 — key 설계, 캐시 히트/미스, Redis 장애 처리.

실제 Redis 서버는 띄우지 않습니다. 서비스 레이어는 conftest의 FakeCache를,
RedisCache 자체는 아래 FakeRedis/BrokenRedis를 주입해 검증합니다.
"""

import pytest
from google.genai import errors as genai_errors

from clients.cache import KEY_PREFIX, NullCache, RedisCache, build_cache, build_cache_key
from conftest import DEFAULT_CANDIDATES, FakeGeminiClient, error_code, success_data
from core.config import settings
from services.translate import TranslateService


def payload(**overrides) -> dict:
    body = {"text": "이거 언제까지 가능해?", "target_lang": "한국어", "style": "general"}
    body.update(overrides)
    return body


# ---------- 캐시 key ----------


def test_cache_key_is_stable_for_same_input():
    assert build_cache_key("안녕", "영어", "sns") == build_cache_key("안녕", "영어", "sns")


@pytest.mark.parametrize(
    "args",
    [
        ("다른 원문", "영어", "sns"),  # text만 다름
        ("안녕", "일본어", "sns"),  # target_lang만 다름
        ("안녕", "영어", "formal"),  # style만 다름
    ],
)
def test_cache_key_differs_when_any_field_differs(args):
    """text / target_lang / style 중 하나라도 다르면 별개의 캐시 항목이어야 합니다.

    key가 세 값을 모두 반영하지 않으면 다른 언어나 다른 스타일 요청이
    남의 캐시 결과를 받아가게 됩니다.
    """
    assert build_cache_key(*args) != build_cache_key("안녕", "영어", "sns")


def test_cache_key_does_not_collide_on_field_boundary():
    """구분자 없이 이어붙이면 충돌하는 조합 — ("ab","c")와 ("a","bc")."""
    assert build_cache_key("ab", "c", "general") != build_cache_key("a", "bc", "general")


def test_cache_key_has_version_prefix():
    """저장 형식이 바뀔 때 과거 캐시를 무시할 수 있도록 버전 prefix가 붙습니다."""
    assert build_cache_key("안녕", "영어", "sns").startswith(f"{KEY_PREFIX}:")


# ---------- 캐시 히트 / 미스 ----------


def test_same_request_twice_calls_gemini_once(client, fake_client):
    """이 이슈의 핵심 — 같은 요청 2번에 Gemini 호출은 1회."""
    first = client.post("/translate", json=payload())
    second = client.post("/translate", json=payload())

    assert len(fake_client.calls) == 1
    assert success_data(first) == success_data(second)


def test_cached_response_matches_first_response(client):
    client.post("/translate", json=payload())
    res = client.post("/translate", json=payload())

    assert success_data(res) == {"candidates": DEFAULT_CANDIDATES, "style": "general"}


@pytest.mark.parametrize(
    "second_payload",
    [
        payload(text="다른 문장"),
        payload(target_lang="영어"),
        payload(style="formal"),
    ],
)
def test_different_request_is_not_served_from_cache(client, fake_client, second_payload):
    client.post("/translate", json=payload())
    client.post("/translate", json=second_payload)

    assert len(fake_client.calls) == 2


def test_result_is_stored_in_cache(client, fake_cache):
    client.post("/translate", json=payload())

    key = build_cache_key("이거 언제까지 가능해?", "한국어", "general")
    assert fake_cache.store[key] == DEFAULT_CANDIDATES


def test_cache_hit_skips_gemini_entirely(client, fake_client, fake_cache):
    """캐시에 미리 값을 넣어두면 Gemini를 한 번도 부르지 않아야 합니다."""
    key = build_cache_key("이거 언제까지 가능해?", "한국어", "general")
    cached = ["미리 캐시된 후보 1", "미리 캐시된 후보 2", "미리 캐시된 후보 3"]
    fake_cache.store[key] = cached

    res = client.post("/translate", json=payload())

    assert fake_client.calls == []
    assert success_data(res)["candidates"] == cached


@pytest.mark.parametrize(
    "stale",
    [
        "문자열 하나",  # v1 시절 형식
        ["후보 1", "후보 2"],  # 개수 부족
        ["후보 1", "후보 2", "후보 3", "후보 4"],  # 개수 초과
        ["후보 1", "  ", "후보 3"],  # 빈 문자열 포함
        [1, 2, 3],  # 문자열 아님
        {"candidates": ["후보 1", "후보 2", "후보 3"]},  # 리스트 아님
    ],
)
def test_malformed_cached_value_is_ignored(client, fake_client, fake_cache, stale):
    """KEY_PREFIX를 올리지 않은 채 저장 형식이 바뀌어도 옛 값이 그대로 나가면 안 됩니다."""
    key = build_cache_key("이거 언제까지 가능해?", "한국어", "general")
    fake_cache.store[key] = stale

    res = client.post("/translate", json=payload())

    assert res.status_code == 200
    assert success_data(res)["candidates"] == DEFAULT_CANDIDATES
    assert len(fake_client.calls) == 1


# ---------- 캐시에 들어가면 안 되는 것 ----------


@pytest.mark.parametrize("bad", [payload(text=""), payload(style="없는스타일")])
def test_validation_error_is_not_cached(client, fake_cache, bad):
    """잘못된 요청은 캐시를 조회하지도, 저장하지도 않아야 합니다."""
    client.post("/translate", json=bad)

    assert fake_cache.keys_requested == []
    assert fake_cache.store == {}


def test_gemini_failure_is_not_cached(client, fake_client, fake_cache):
    """실패를 캐싱하면 TTL 동안 계속 실패하게 됩니다."""

    def boom(contents, system_instruction):
        raise genai_errors.APIError(503, {"error": {"message": "service unavailable"}})

    fake_client.generate = boom

    res = client.post("/translate", json=payload())

    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"
    assert fake_cache.store == {}


# ---------- 캐시가 없거나 죽었을 때 ----------


def test_service_works_without_cache():
    """캐시를 주입하지 않으면 NullCache로 동작 — 매번 호출하지만 실패하지는 않습니다."""
    fake = FakeGeminiClient()
    service = TranslateService(fake)

    assert service.translate("안녕", "영어", "general") == DEFAULT_CANDIDATES
    assert service.translate("안녕", "영어", "general") == DEFAULT_CANDIDATES
    assert len(fake.calls) == 2


def test_null_cache_always_misses():
    cache = NullCache()
    cache.set("key", "value")

    assert cache.get("key") is None


class FakeRedis:
    """redis 클라이언트 대역 (decode_responses=True 가정)."""

    def __init__(self):
        self.store: dict = {}
        self.ttls: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex


class BrokenRedis:
    """모든 명령이 실패하는 Redis — 연결 끊김/타임아웃 상황."""

    def get(self, key):
        raise ConnectionError("redis 연결 실패")

    def set(self, key, value, ex=None):
        raise ConnectionError("redis 연결 실패")


def test_redis_cache_roundtrip():
    cache = RedisCache(FakeRedis(), ttl_seconds=60)
    cache.set("key", "번역 결과")

    assert cache.get("key") == "번역 결과"


def test_redis_cache_stores_json_so_value_type_survives():
    """리스트를 넣으면 리스트로 돌아와야 합니다 — 캐시에 담는 값이 후보 리스트이므로."""
    cache = RedisCache(FakeRedis(), ttl_seconds=60)
    cache.set("key", ["후보1", "후보2", "후보3"])

    assert cache.get("key") == ["후보1", "후보2", "후보3"]


def test_redis_cache_applies_ttl():
    fake_redis = FakeRedis()
    RedisCache(fake_redis, ttl_seconds=123).set("key", "값")

    assert fake_redis.ttls["key"] == 123


def test_redis_cache_stores_korean_readably():
    """운영 중 redis-cli로 들여다볼 일이 많아 \\uXXXX로 저장되면 곤란합니다."""
    fake_redis = FakeRedis()
    RedisCache(fake_redis, ttl_seconds=60).set("key", "한국어")

    assert "한국어" in fake_redis.store["key"]


def test_redis_failure_on_get_is_treated_as_miss():
    """Redis가 죽어도 예외가 아니라 miss로 처리되어야 합니다."""
    assert RedisCache(BrokenRedis(), ttl_seconds=60).get("key") is None


def test_redis_failure_on_set_does_not_raise():
    RedisCache(BrokenRedis(), ttl_seconds=60).set("key", "값")


def test_corrupted_cache_value_is_treated_as_miss():
    """형식이 깨진 값이 들어 있어도 번역이 실패하면 안 됩니다."""
    fake_redis = FakeRedis()
    fake_redis.store["key"] = "{망가진 JSON"

    assert RedisCache(fake_redis, ttl_seconds=60).get("key") is None


def test_translate_still_works_when_redis_is_down(fake_client):
    """엔드-투-엔드 — Redis 장애 시 캐시만 건너뛰고 번역은 정상 동작."""
    service = TranslateService(fake_client, RedisCache(BrokenRedis(), ttl_seconds=60))

    assert service.translate("안녕", "영어", "general") == DEFAULT_CANDIDATES
    assert len(fake_client.calls) == 1


# ---------- 캐시 구성 ----------


def test_build_cache_returns_null_cache_without_redis_url(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")

    assert isinstance(build_cache(), NullCache)


def test_build_cache_returns_null_cache_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    assert isinstance(build_cache(), NullCache)


def test_build_cache_returns_redis_cache_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    # from_url()은 지연 연결이라 Redis가 떠 있지 않아도 이 호출은 성공해야 합니다.
    assert isinstance(build_cache(), RedisCache)
