"""테스트 공용 fixture.

실제 Gemini API는 호출하지 않습니다. FakeGeminiClient를 DI로 주입합니다.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.routes import get_translate_service
from main import app
from services.translate import TranslateService

DEFAULT_CANDIDATES = ["번역 후보 1", "번역 후보 2", "번역 후보 3"]
DEFAULT_REPLY = json.dumps(DEFAULT_CANDIDATES, ensure_ascii=False)


def error_message(response) -> str:
    """에러 응답에서 사람이 읽을 메시지를 꺼냅니다.

    백엔드는 {"success": false, "error": {"code", "message"}} 공통 envelope을 씁니다.
    형식이 또 바뀌면 이 함수만 수정하면 전체 테스트가 따라옵니다. 테스트 본문에서
    response.json()["error"]를 직접 읽지 마세요.
    """
    return response.json()["error"]["message"]


def error_code(response) -> str:
    """에러 응답에서 머신 리더블 코드를 꺼냅니다 (error_message()와 동일한 용도)."""
    return response.json()["error"]["code"]


def success_data(response):
    """성공 응답에서 실제 데이터를 꺼냅니다 ({"success": true, "data": ...} 언랩).

    error_message()/error_code()와 같은 이유 — envelope이 또 바뀌면 여기만 고치면 됩니다.
    """
    body = response.json()
    assert body["success"] is True
    return body["data"]


class FakeGeminiClient:
    """GeminiClient 대역. 호출 인자를 기록해 프롬프트 조립을 검증할 수 있습니다."""

    def __init__(self, *, configured: bool = True, reply: str = DEFAULT_REPLY):
        self._configured = configured
        self.reply = reply
        self.calls: list[dict] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    def generate(self, contents: str, system_instruction: str) -> str:
        self.calls.append({"contents": contents, "system_instruction": system_instruction})
        return self.reply


class FakeCache:
    """TranslationCache 대역. 실제 Redis 없이 hit/miss를 검증합니다.

    구현이 아니라 프로토콜에만 의존하므로 테스트에 Redis 서버가 필요 없습니다
    (FakeGeminiClient와 같은 이유).
    """

    def __init__(self):
        self.store: dict = {}
        self.keys_requested: list = []

    def get(self, key: str):
        self.keys_requested.append(key)
        return self.store.get(key)

    def set(self, key: str, value) -> None:
        self.store[key] = value


@pytest.fixture
def fake_client():
    return FakeGeminiClient()


@pytest.fixture
def fake_cache():
    return FakeCache()


@pytest.fixture
def client(fake_client, fake_cache):
    """FakeGeminiClient와 FakeCache가 주입된 TestClient."""
    app.dependency_overrides[get_translate_service] = lambda: TranslateService(
        fake_client, fake_cache
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_client():
    """원하는 상태의 가짜 클라이언트로 TestClient를 만드는 팩토리.

    사용: test_client, fake = make_client(configured=False)

    raise_server_exceptions=False를 넘기면 전역 Exception 핸들러가 만든 응답을 그대로
    돌려받습니다 (기본 TestClient는 핸들러가 처리한 뒤에도 원본 예외를 다시 raise함 —
    프로덕션에서는 응답이 이미 전송된 뒤라 무해하지만 테스트에선 검증을 방해함).
    """

    def _make(*, raise_server_exceptions: bool = True, **kwargs):
        fake = FakeGeminiClient(**kwargs)
        app.dependency_overrides[get_translate_service] = lambda: TranslateService(
            fake, FakeCache()
        )
        return TestClient(app, raise_server_exceptions=raise_server_exceptions), fake

    yield _make
    app.dependency_overrides.clear()
