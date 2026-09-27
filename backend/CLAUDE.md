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
| `clients/cache.py` | `TranslationCache` 프로토콜 + `RedisCache` / `NullCache`. 싱글톤 `translation_cache` |
| `core/config.py` | `Settings` — 환경변수, 모델명, CORS 허용 오리진, 캐시 설정 |
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
- `POST /translate` — `{text, target_lang, style}` → `{candidates: [str, str, str], style}` (서로 다른 번역 후보 3개)

에러는 `services/translate.py`가 `AppError` 하위 예외를 raise하고
`core/error_handlers.py`가 `{"success": false, "error": {"code", "message"}}`로 변환합니다.
서비스 레이어는 FastAPI에 의존하지 않습니다.

| 조건 | status | code |
|---|---|---|
| API 키 미설정 | 500 | `API_KEY_NOT_CONFIGURED` |
| 알 수 없는 스타일 | 400 | `UNKNOWN_STYLE` |
| 빈 텍스트 | 400 | `EMPTY_TEXT` |
| Gemini 호출 실패 / 응답이 문자열 3개 배열이 아님 | 502 | `TRANSLATION_ENGINE_ERROR` |
| 요청 스키마 검증 실패 | 422 | `VALIDATION_ERROR` (`RequestValidationError` 핸들러) |
| 그 외 미처리 예외 | 500 | `INTERNAL_ERROR` (원문은 로그로만, 클라이언트엔 비노출) |

## Gemini 호출

`clients/gemini.py` — 모델 `gemini-3.5-flash`, temperature 0.3, max_output_tokens 4096.
structured output(`response_mime_type="application/json"`, `response_schema=list[str]`)으로 JSON 문자열 배열을 받고,
`TranslateService._parse_candidates()`가 후보 `CANDIDATE_COUNT`(3)개인지 검증합니다.
`GEMINI_API_KEY`가 없으면 `_client=None`이 되고 `is_configured`가 False (import 자체는 성공하므로 CI에서 키 없이 테스트 가능).

프롬프트는 `TranslateService._build_system_prompt()`에서 `target_lang` + 스타일 `description` + few-shot `examples`를 한국어 시스템 지시문에 주입하고, 서로 다른 후보 3개를 JSON 배열로 출력하라는 지시로 끝납니다.
`FakeGeminiClient`의 `reply`도 JSON 배열 문자열이어야 합니다 (`conftest.DEFAULT_REPLY`).

## Caching

`POST /translate`는 같은 `(text, target_lang, style)` 조합이면 Gemini를 다시 부르지 않습니다.

- key는 세 값을 JSON 배열로 직렬화한 뒤 sha256 (`build_cache_key()`). 버전 prefix `translate:v2`가
  붙어 있으니 **저장하는 값의 형식을 바꾸면 `KEY_PREFIX`를 올리고 선언부 이력에 한 줄 추가하세요**
  — 과거 캐시가 자동으로 무시됩니다.
- 버전을 올리는 것을 잊어도 캐시에서 꺼낸 값은 `_is_valid_candidates()`로 형식을 검증합니다.
  어긋나면 miss로 처리되고 새로 번역합니다 (모델 응답 검증과 같은 함수를 씁니다).
- 값은 JSON으로 직렬화해 저장합니다. Redis가 문자열만 담기 때문이고, 덕분에 저장 값의 타입이
  바뀌어도 `RedisCache`는 그대로 둘 수 있습니다.
- `TranslateService`는 `clients/cache.py`의 프로토콜에만 의존합니다. Redis를 직접 알지 못하므로
  테스트에 Redis 서버가 필요 없습니다.
- **캐시 실패는 절대 요청을 죽이지 않습니다.** `RedisCache`의 `get()`/`set()`은 모든 예외를 삼키고
  로그만 남깁니다 — Redis가 죽으면 느려질 뿐 번역은 정상 동작해야 합니다.
- 검증 실패와 Gemini 호출 실패는 캐싱하지 않습니다 (실패를 캐싱하면 TTL 동안 계속 실패).

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `REDIS_URL` | `""` | 비어 있으면 `NullCache` — 캐시 없이 동작 |
| `CACHE_ENABLED` | `true` | `false`면 `REDIS_URL`이 있어도 캐시 끔 |
| `CACHE_TTL_SECONDS` | `3600` | 캐시 항목 만료 시간 |

로컬에서 Redis 없이 개발해도 됩니다. `REDIS_URL`을 비워두면 매번 Gemini를 호출할 뿐입니다.

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
- 캐시도 같은 방식입니다 — `conftest.py`의 `FakeCache`가 `client` fixture에 주입되며,
  `fake_cache` fixture로 저장된 내용을 들여다볼 수 있습니다. 테스트는 Redis 없이 돕니다.
