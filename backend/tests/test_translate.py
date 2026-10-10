"""POST /translate — 정상 케이스 + 에러 케이스.

에러 메시지 단정은 conftest.error_message()를 거칩니다.
응답 형식이 바뀌면 그 헬퍼만 고치면 됩니다.
"""

import asyncio
import json
import logging

import httpx
import pytest
from google.genai import errors as genai_errors

from api.routes import get_rate_limiter, get_translate_service
from conftest import DEFAULT_CANDIDATES, DEFAULT_REPLY, error_code, error_message, success_data
from core.config import settings
from core.exceptions import TranslationEngineError
from main import app
from services.chunking import chunk_text
from services.translate import CONTEXT_TAIL_CHARS, SHORT_LIMIT, TranslateService
from styles import STYLES


def payload(**overrides) -> dict:
    body = {"text": "이거 언제까지 가능해?", "target_lang": "한국어", "style": "general"}
    body.update(overrides)
    return body


# ---------- 정상 케이스 ----------


def test_translate_returns_candidates(client):
    res = client.post("/translate", json=payload())

    assert res.status_code == 200
    assert success_data(res) == {"candidates": DEFAULT_CANDIDATES, "style": "general"}


@pytest.mark.parametrize("style", sorted(STYLES))
def test_translate_accepts_every_defined_style(client, style):
    """STYLES에 스타일을 추가해도 엔드포인트가 받아주는지 자동으로 검증."""
    res = client.post("/translate", json=payload(style=style))

    assert res.status_code == 200
    assert success_data(res)["style"] == style


def test_translate_strips_whitespace_from_model_output(make_client):
    test_client, _ = make_client(reply=json.dumps(["  후보 1  \n", "후보 2 ", " 후보 3"]))

    res = test_client.post("/translate", json=payload())
    assert success_data(res)["candidates"] == ["후보 1", "후보 2", "후보 3"]


def test_translate_passes_text_and_style_prompt_to_client(client, fake_client):
    """프롬프트 조립 검증 — 원문, 대상 언어, 스타일 설명, few-shot 예시가 들어가야 함."""
    client.post("/translate", json=payload(text="안녕", target_lang="영어", style="sns"))

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["contents"] == "안녕"
    prompt = call["system_instruction"]
    assert "영어" in prompt
    assert STYLES["sns"]["description"] in prompt
    assert STYLES["sns"]["examples"][0]["source"] in prompt
    assert "후보 3개" in prompt


# ---------- 에러 케이스 ----------


def test_translate_rejects_unknown_style(client):
    res = client.post("/translate", json=payload(style="존재하지_않는_스타일"))

    assert res.status_code == 400
    assert "존재하지_않는_스타일" in error_message(res)
    assert error_code(res) == "UNKNOWN_STYLE"


def test_translate_rejects_empty_text(client):
    res = client.post("/translate", json=payload(text=""))

    assert res.status_code == 400
    assert "비어" in error_message(res)
    assert error_code(res) == "EMPTY_TEXT"


def test_translate_rejects_whitespace_only_text(client):
    res = client.post("/translate", json=payload(text="   \n\t  "))

    assert res.status_code == 400


def test_translate_does_not_call_client_on_validation_error(client, fake_client):
    """검증 실패 시 Gemini 호출이 일어나지 않아야 함 (불필요한 과금 방지)."""
    client.post("/translate", json=payload(style="없는스타일"))
    client.post("/translate", json=payload(text=""))

    assert fake_client.calls == []


def test_translate_fails_when_api_key_missing(make_client):
    test_client, _ = make_client(configured=False)

    res = test_client.post("/translate", json=payload())

    assert res.status_code == 500
    assert "GEMINI_API_KEY" in error_message(res)
    assert error_code(res) == "API_KEY_NOT_CONFIGURED"


def test_translate_returns_502_when_gemini_fails(make_client):
    """Gemini 장애는 서버 오류(500)가 아니라 업스트림 오류(502)로 나가야 함."""
    test_client, fake = make_client()

    async def boom(contents, system_instruction):
        raise genai_errors.APIError(503, {"error": {"message": "service unavailable"}})

    fake.generate = boom

    res = test_client.post("/translate", json=payload())

    assert res.status_code == 502
    assert "번역 엔진" in error_message(res)
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"


@pytest.mark.parametrize(
    "reply",
    [
        "JSON이 아닌 응답",
        json.dumps(["후보 1", "후보 2"]),
        json.dumps(["후보 1", "후보 2", "후보 3", "후보 4"]),
        json.dumps(["후보 1", "  ", "후보 3"]),
        json.dumps({"candidates": ["후보 1", "후보 2", "후보 3"]}),
    ],
)
def test_translate_returns_502_when_model_output_is_malformed(make_client, caplog, reply):
    """모델이 약속한 형식(문자열 3개 배열)을 어기면 업스트림 오류(502)로 처리."""
    test_client, _ = make_client(reply=reply)

    with caplog.at_level(logging.WARNING, logger="services.translate"):
        res = test_client.post("/translate", json=payload())

    assert res.status_code == 502
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"
    assert "model output malformed" in caplog.text


def test_translate_returns_500_with_generic_message_on_unexpected_error(make_client):
    """AppError가 아닌 예외는 전역 핸들러가 잡아 내부 정보 없이 500을 반환해야 함."""
    test_client, fake = make_client(raise_server_exceptions=False)

    async def boom(contents, system_instruction):
        raise RuntimeError("내부 디버그 정보 - 절대 노출 금지")

    fake.generate = boom

    res = test_client.post("/translate", json=payload())

    assert res.status_code == 500
    assert "디버그" not in res.text
    assert error_message(res) == "서버 오류가 발생했습니다."
    assert error_code(res) == "INTERNAL_ERROR"


# ---------- 스키마 검증 (FastAPI/Pydantic 기본 422) ----------


@pytest.mark.parametrize("missing", ["text", "target_lang", "style"])
def test_translate_requires_all_fields(client, missing):
    body = payload()
    del body[missing]

    assert client.post("/translate", json=body).status_code == 422


def test_translate_rejects_wrong_type(client):
    assert client.post("/translate", json=payload(text=123)).status_code == 422


def test_translate_rejects_text_over_short_limit(client, fake_client):
    """짧은 번역 한도를 넘으면 Gemini를 부르지 않고 장문 엔드포인트를 안내해야 함."""
    res = client.post("/translate", json=payload(text="가" * (SHORT_LIMIT + 1)))

    assert res.status_code == 400
    assert error_code(res) == "TRANSLATE_ERROR"
    assert "/translate/long" in error_message(res)
    assert fake_client.calls == []


def test_translate_rejects_text_over_max_length(client):
    res = client.post("/translate", json=payload(text="가" * 10001))

    assert res.status_code == 422
    assert error_code(res) == "VALIDATION_ERROR"


# ---------- POST /translate/long (장문, 청크별 1개) ----------

ONE_REPLY = json.dumps(["번역"], ensure_ascii=False)


def test_translate_long_short_text_calls_once(make_client):
    test_client, fake = make_client(reply=ONE_REPLY)

    res = test_client.post("/translate/long", json=payload())

    assert res.status_code == 200
    assert success_data(res) == {"translation": "번역", "style": "general"}
    assert len(fake.calls) == 1
    assert "1개" in fake.calls[0]["system_instruction"]


def test_translate_long_chunks_and_keeps_paragraphs(make_client):
    test_client, fake = make_client(reply=ONE_REPLY)
    text = "가" * 1500 + "\n\n" + "나" * 1500

    res = test_client.post("/translate/long", json=payload(text=text))

    assert success_data(res)["translation"] == "번역\n\n번역"
    assert [c["contents"] for c in fake.calls] == ["가" * 1500, "나" * 1500]


def test_translate_long_rejects_text_over_max_length(client):
    res = client.post("/translate/long", json=payload(text="가" * 10001))

    assert res.status_code == 422


def test_translate_long_returns_502_when_gemini_fails(make_client):
    test_client, fake = make_client()

    async def boom(contents, system_instruction):
        raise genai_errors.APIError(503, {"error": {"message": "service unavailable"}})

    fake.generate = boom

    res = test_client.post("/translate/long", json=payload())

    assert res.status_code == 502
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"


# ---------- POST /translate/long — 용어집 선추출 / 앞 청크 문맥 (#23) ----------

TWO_CHUNKS = "가" * 1500 + "\n\n" + "나" * 1500


def test_translate_long_single_chunk_skips_glossary(make_client):
    test_client, fake = make_client(reply=ONE_REPLY)

    res = test_client.post("/translate/long", json=payload())

    assert res.status_code == 200
    assert fake.glossary_calls == []
    assert "용어집" not in fake.calls[0]["system_instruction"]
    assert "참고용 앞 문맥" not in fake.calls[0]["system_instruction"]


def test_translate_long_extracts_glossary_once_and_puts_it_in_every_chunk(make_client):
    test_client, fake = make_client(reply=ONE_REPLY)

    res = test_client.post("/translate/long", json=payload(text=TWO_CHUNKS))

    assert res.status_code == 200
    assert [c["contents"] for c in fake.glossary_calls] == [TWO_CHUNKS]
    assert len(fake.calls) == 2
    assert all("철수 → Cheolsu" in c["system_instruction"] for c in fake.calls)


def test_translate_long_passes_previous_chunk_tail_as_context(make_client):
    test_client, fake = make_client(reply=ONE_REPLY)
    first = "가" * 1500 + "앞 청크의 마지막 문장."
    text = first + "\n\n" + "나" * 1500

    res = test_client.post("/translate/long", json=payload(text=text))

    assert success_data(res)["translation"] == "번역\n\n번역"
    head, tail = fake.calls
    assert "참고용 앞 문맥" not in head["system_instruction"]
    assert first[-CONTEXT_TAIL_CHARS:] in tail["system_instruction"]
    assert first[-CONTEXT_TAIL_CHARS - 1 :] not in tail["system_instruction"]
    # 참고 문맥은 시스템 지시문에만 — 번역 대상(contents)에는 섞이지 않아야 합니다.
    assert tail["contents"] == "나" * 1500


@pytest.mark.parametrize(
    "glossary_reply",
    [
        genai_errors.APIError(503, {"error": {"message": "service unavailable"}}),
        TranslationEngineError("잘림"),
        "not json",
        json.dumps({"source": "철수", "target": "Cheolsu"}),  # 배열이 아님
        json.dumps([{"source": "철수"}]),  # target 누락
        json.dumps([{"source": " ", "target": "Cheolsu"}]),  # 빈 용어
    ],
    ids=["api-error", "engine-error", "invalid-json", "not-list", "missing-field", "blank-term"],
)
def test_translate_long_fails_open_when_glossary_extraction_fails(make_client, caplog, glossary_reply):
    test_client, fake = make_client(reply=ONE_REPLY, glossary_reply=glossary_reply)

    with caplog.at_level(logging.WARNING, logger="services.translate"):
        res = test_client.post("/translate/long", json=payload(text=TWO_CHUNKS))

    assert success_data(res)["translation"] == "번역\n\n번역"
    assert all("용어집" not in c["system_instruction"] for c in fake.calls)
    assert "glossary extraction failed" in caplog.text


def test_translate_long_fails_open_when_glossary_extraction_times_out(make_client, caplog, monkeypatch):
    monkeypatch.setattr(settings, "GLOSSARY_TIMEOUT_SECONDS", 0.01)
    test_client, fake = make_client(reply=ONE_REPLY)
    original = fake.generate

    async def slow_glossary(contents, system_instruction, **options):
        if "response_schema" in options:
            await asyncio.sleep(1)
        return await original(contents, system_instruction, **options)

    fake.generate = slow_glossary

    with caplog.at_level(logging.WARNING, logger="services.translate"):
        res = test_client.post("/translate/long", json=payload(text=TWO_CHUNKS))

    assert success_data(res)["translation"] == "번역\n\n번역"
    assert all("용어집" not in c["system_instruction"] for c in fake.calls)
    assert "TimeoutError" in caplog.text


def test_translate_long_translates_chunks_concurrently(make_client):
    """청크 번역은 병렬이어야 합니다 — 가짜 Gemini는 모든 청크 호출이 도착해야 응답합니다.

    순차 호출이면 첫 청크가 나머지를 기다리다 타임아웃으로 실패합니다.
    """
    test_client, fake = make_client(reply=ONE_REPLY)
    text = "\n\n".join(c * 1500 for c in "가나다")
    arrived = 0
    all_arrived = asyncio.Event()

    async def wait_for_every_chunk(contents, system_instruction, **options):
        nonlocal arrived
        if "response_schema" in options:
            return fake.glossary_reply
        arrived += 1
        if arrived == 3:
            all_arrived.set()
        await asyncio.wait_for(all_arrived.wait(), timeout=2)
        return ONE_REPLY

    fake.generate = wait_for_every_chunk

    res = test_client.post("/translate/long", json=payload(text=text))

    assert success_data(res)["translation"] == "번역\n\n번역\n\n번역"


def test_translate_long_cancels_other_chunks_when_one_fails(make_client):
    """청크 하나가 실패하면 나머지 청크 호출은 취소되어야 합니다 — 결과가 502인데 쿼터만 쓰지 않도록."""
    test_client, fake = make_client(reply=ONE_REPLY)
    text = "\n\n".join(c * 1500 for c in "가나다")
    cancelled = []

    async def first_chunk_fails(contents, system_instruction, **options):
        if "response_schema" in options:
            return fake.glossary_reply
        if contents.startswith("가"):
            raise genai_errors.APIError(503, {"error": {"message": "service unavailable"}})
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(contents[0])
            raise
        return ONE_REPLY

    fake.generate = first_chunk_fails

    res = test_client.post("/translate/long", json=payload(text=text))

    assert res.status_code == 502
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"
    assert sorted(cancelled) == ["나", "다"]


def test_chunk_text_preserves_text_and_respects_limit():
    text = "짧은 문단.\n\n" + "긴 문장입니다. " * 300 + "\n\n" + "가" * 4500
    chunks = chunk_text(text)

    assert "".join(chunks) == text
    assert all(len(c) <= 2000 for c in chunks)


# ---------- 동시 처리 (async I/O) ----------


@pytest.mark.anyio
async def test_requests_wait_for_gemini_concurrently(fake_client, fake_cache, fake_rate_limiter):
    """Gemini 응답을 기다리는 동안 다른 요청도 처리되어야 합니다 — async 전환(#20)의 목적.

    가짜 Gemini는 요청 n개가 모두 도착해야 응답합니다. 요청이 하나씩 처리되면 첫 요청이
    나머지를 기다리다 타임아웃으로 실패합니다. TestClient는 요청을 하나씩 보내므로
    httpx.AsyncClient로 n개를 동시에 보냅니다.
    """
    n = 5
    arrived = 0
    all_arrived = asyncio.Event()

    async def wait_for_everyone(contents, system_instruction):
        nonlocal arrived
        arrived += 1
        if arrived == n:
            all_arrived.set()
        await asyncio.wait_for(all_arrived.wait(), timeout=2)
        return DEFAULT_REPLY

    fake_client.generate = wait_for_everyone
    app.dependency_overrides[get_translate_service] = lambda: TranslateService(fake_client, fake_cache)
    app.dependency_overrides[get_rate_limiter] = lambda: fake_rate_limiter
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            responses = await asyncio.gather(
                *(ac.post("/translate", json=payload(text=f"문장 {i}")) for i in range(n))
            )
    finally:
        app.dependency_overrides.clear()

    assert [r.status_code for r in responses] == [200] * n
