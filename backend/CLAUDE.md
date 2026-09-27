# Backend — CLAUDE.md

FastAPI 앱. 레이어 분리 구조 (router → service → client).

## Commands

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000     # Swagger: http://localhost:8000/docs
pip install -r requirements.txt
pytest                                    # 테스트 (pytest.ini: pythonpath=., testpaths=tests)
```

## Layers

| 파일 | 역할 |
|---|---|
| `main.py` | FastAPI 인스턴스, CORS 미들웨어, 라우터 등록 |
| `api/routes.py` | 엔드포인트 3개 + `get_translate_service()` DI 팩토리 |
| `services/translate.py` | `TranslateService` — 검증, 프롬프트 조립, 클라이언트 호출 |
| `clients/gemini.py` | `GeminiClient` — Gemini SDK 래퍼. 모듈 로드 시 싱글톤 `gemini_client` 생성 |
| `core/config.py` | `Settings` — 환경변수, 모델명, CORS 허용 오리진 |
| `core/envelope.py` | `SuccessResponse[T]` — 성공 응답 공통 껍데기 |
| `core/exceptions.py` | `AppError` 및 하위 예외 — FastAPI를 모르는 순수 도메인 예외 |
| `core/error_handlers.py` | `AppError` / 검증 실패 / 미처리 예외 → HTTP 변환. `register_exception_handlers(app)` |
| `models/schemas.py` | `TranslateRequest` / `TranslateResponse` / `HealthData` |
| `styles.py` | `STYLES` 딕셔너리 — 스타일 단일 정의처 |

## Endpoints

성공 응답은 모두 `{"success": true, "data": ...}`로 감싸집니다 (`SuccessResponse[T]`).
아래 표기는 `data` 안쪽입니다.

- `GET /health` → `{"status": "ok", "api_key_configured": bool}`
- `GET /styles` → `{key: label}` (`STYLES`에서 생성)
- `POST /translate` — `{text, target_lang, style}` (text ≤ 10,000자) → `{candidates: [...], style}`
  - 청크 1개(≤ 2,000자): 서로 다른 번역 후보 3개
  - 청크 2개 이상: 청크별 번역을 이어붙인 결과 1개

에러는 `services/translate.py`가 `AppError` 하위 예외를 raise하고
`core/error_handlers.py`가 `{"success": false, "error": {"code", "message"}}`로 변환합니다.
서비스 레이어는 FastAPI에 의존하지 않습니다.

| 조건 | status | code |
|---|---|---|
| API 키 미설정 | 500 | `API_KEY_NOT_CONFIGURED` |
| 알 수 없는 스타일 | 400 | `UNKNOWN_STYLE` |
| 빈 텍스트 | 400 | `EMPTY_TEXT` |
| Gemini 호출 실패 / 응답이 요청한 개수의 문자열 배열이 아님 | 502 | `TRANSLATION_ENGINE_ERROR` |
| 요청 스키마 검증 실패 | 422 | `VALIDATION_ERROR` (`RequestValidationError` 핸들러) |
| 그 외 미처리 예외 | 500 | `INTERNAL_ERROR` (원문은 로그로만, 클라이언트엔 비노출) |

## Gemini 호출

`clients/gemini.py` — 모델 `gemini-3.5-flash`, temperature 0.3, max_output_tokens 4096.
structured output(`response_mime_type="application/json"`, `response_schema=list[str]`)으로 JSON 문자열 배열을 받고,
`TranslateService._parse_candidates()`가 요청한 후보 개수인지 검증합니다.

입력은 `chunk_text()`가 문단 → 문장 → 글자 순으로 `CHUNK_SIZE`(2,000자) 이하 청크로 나눕니다.
청크 1개면 호출 1번에 후보 `CANDIDATE_COUNT`(3)개, 2개 이상이면 청크마다 순차 호출해 후보 1개씩 받고
원문의 구분 공백을 끼워 이어붙입니다 (`"".join(chunks) == text` 불변식).
`GEMINI_API_KEY`가 없으면 `_client=None`이 되고 `is_configured`가 False (import 자체는 성공하므로 CI에서 키 없이 테스트 가능).

프롬프트는 `TranslateService._build_system_prompt()`에서 `target_lang` + 스타일 `description` + few-shot `examples`를 한국어 시스템 지시문에 주입하고, 서로 다른 후보 3개를 JSON 배열로 출력하라는 지시로 끝납니다.
`FakeGeminiClient`의 `reply`도 JSON 배열 문자열이어야 합니다 (`conftest.DEFAULT_REPLY`).

## Adding a Style

`styles.py`의 `STYLES`에 항목 추가만 하면 됩니다 (현재 `general` / `formal` / `sns`).
프론트엔드는 `/styles`로 자동 반영되므로 다른 수정 불필요.

```python
"your_key": {
    "label": "UI에 표시될 이름",
    "description": "시스템 프롬프트에 들어갈 스타일 설명",
    "examples": [{"source": "원문 예시", "target": "스타일 적용 예시"}],
},
```

## Testing

`tests/conftest.py`에 `FakeGeminiClient`와 `client` fixture가 있습니다.
실제 Gemini API를 호출하지 않으며, `app.dependency_overrides[get_translate_service]`로 주입합니다.

- **응답 형식을 단정할 때는 `conftest.py`의 헬퍼를 쓰세요** — `success_data()`,
  `error_message()`, `error_code()`. envelope이 또 바뀌면 그 세 함수만 고치면 전체 테스트가
  따라옵니다. 테스트 본문에서 `response.json()["data"]`를 직접 읽지 마세요.
- 전역 `Exception` 핸들러가 만든 응답을 검증하려면 `make_client(raise_server_exceptions=False)`를
  쓰세요. 기본 `TestClient`는 핸들러 처리 후에도 원본 예외를 다시 raise합니다.
- `GET /health`는 DI를 거치지 않고 전역 `gemini_client`를 직접 읽습니다 (`api/routes.py`).
  따라서 `dependency_overrides`가 통하지 않고 `monkeypatch`가 필요합니다.
