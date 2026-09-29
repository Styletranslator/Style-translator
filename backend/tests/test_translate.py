"""POST /translate — 정상 케이스 + 에러 케이스.

에러 메시지 단정은 conftest.error_message()를 거칩니다.
응답 형식이 바뀌면 그 헬퍼만 고치면 됩니다.
"""

import json

import pytest
from google.genai import errors as genai_errors

from conftest import DEFAULT_CANDIDATES, error_code, error_message, success_data
from services.chunking import chunk_text
from services.translate import SHORT_LIMIT
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

    def boom(contents, system_instruction):
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
def test_translate_returns_502_when_model_output_is_malformed(make_client, reply):
    """모델이 약속한 형식(문자열 3개 배열)을 어기면 업스트림 오류(502)로 처리."""
    test_client, _ = make_client(reply=reply)

    res = test_client.post("/translate", json=payload())

    assert res.status_code == 502
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"


def test_translate_returns_500_with_generic_message_on_unexpected_error(make_client):
    """AppError가 아닌 예외는 전역 핸들러가 잡아 내부 정보 없이 500을 반환해야 함."""
    test_client, fake = make_client(raise_server_exceptions=False)

    def boom(contents, system_instruction):
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


def test_translate_rejects_text_over_max_length(client):
    res = client.post("/translate", json=payload(text="가" * (SHORT_LIMIT + 1)))

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

    def boom(contents, system_instruction):
        raise genai_errors.APIError(503, {"error": {"message": "service unavailable"}})

    fake.generate = boom

    res = test_client.post("/translate/long", json=payload())

    assert res.status_code == 502
    assert error_code(res) == "TRANSLATION_ENGINE_ERROR"


def test_chunk_text_preserves_text_and_respects_limit():
    text = "짧은 문단.\n\n" + "긴 문장입니다. " * 300 + "\n\n" + "가" * 4500
    chunks = chunk_text(text)

    assert "".join(chunks) == text
    assert all(len(c) <= 2000 for c in chunks)
