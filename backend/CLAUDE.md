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
| `main.py` | FastAPI 인스턴스, CORS 미들웨어, 라우터 등록, 종료 시 Redis 연결 풀 닫기 (`lifespan`) |
| `api/routes.py` | 엔드포인트 4개 + `get_translate_service()` / `get_rate_limiter()` DI 팩토리 + `enforce_rate_limit` |
| `services/translate.py` | `TranslateService` — 검증, 프롬프트 조립, 클라이언트 호출 |
| `services/chunking.py` | `chunk_text()` — 장문을 문단 → 문장 → 글자 순으로 `CHUNK_SIZE` 이하 청크로 분할 (순수 함수) |
| `clients/gemini.py` | `GeminiClient` — Gemini SDK 래퍼 (비동기 API `client.aio`). 모듈 로드 시 싱글톤 `gemini_client` 생성 |
| `clients/redis_client.py` | 공용 비동기 Redis 클라이언트 (`redis.asyncio`, 타임아웃 설정 포함). 싱글톤 `redis_client` — 캐시와 rate limiter가 공유 |
| `clients/cache.py` | `TranslationCache` 프로토콜 + `RedisCache` / `NullCache`. 싱글톤 `translation_cache` |
| `clients/rate_limiter.py` | `RateLimiter` 프로토콜 + `RedisRateLimiter` / `NullRateLimiter`. 싱글톤 `rate_limiter` |
| `core/config.py` | `Settings` — 환경변수, 모델명, CORS 허용 오리진, 캐시 / rate limit 설정 |
| `core/envelope.py` | `SuccessResponse[T]` — 성공 응답 공통 껍데기 |
| `core/exceptions.py` | `AppError` 및 하위 예외 — FastAPI를 모르는 순수 도메인 예외 |
| `core/error_handlers.py` | `AppError` / 검증 실패 / 미처리 예외 → HTTP 변환. `register_exception_handlers(app)` |
| `models/schemas.py` | `TranslateRequest` (두 번역 엔드포인트 공용, text ≤ 10,000자) / `TranslateResponse` / `LongTranslateResponse` / `HealthData` / `GlossaryTerm` (용어집 추출 스키마) |
| `styles.py` | `STYLES` 딕셔너리 — 스타일 단일 정의처 |

## Async

Redis와 Gemini를 부르는 경로는 모두 `async`입니다 — `/translate`, `/translate/long` 라우트,
`enforce_rate_limit`, `TranslateService.translate()` / `translate_long()`, 캐시 `get/set`, rate limiter `hit()`,
`GeminiClient.generate()`. I/O를 기다리는 동안 이벤트 루프가 다른 요청을 처리합니다.

- **async 함수 안에서 동기 블로킹 호출을 하지 마세요.** 동기 Redis 클라이언트, Gemini 동기 API
  (`client.models...`, `client.aio` 없이), `time.sleep`, `requests` 등이 하나라도 있으면 그동안
  이벤트 루프 전체가 멈춰 모든 요청이 함께 멈춥니다. 스레드풀에서 돌던 동기 라우트 시절보다 피해가 큽니다.
- 새 Redis/Gemini 호출을 추가할 때는 반드시 `await`하는 비동기 API를 쓰세요.
- `/health`, `/styles`는 I/O가 없어 동기 `def`로 둡니다 (FastAPI가 스레드풀에서 실행).
- `translate_long()`은 청크를 `asyncio.gather`로 병렬 번역합니다 (아래 "Gemini 호출" 참고).
  청크 하나라도 실패하면 나머지 청크 호출을 취소하고 원래 예외(→ 502)를 올립니다.
  `asyncio.TaskGroup`은 예외를 `ExceptionGroup`으로 감싸 에러 핸들러가 500으로 처리하므로 쓰지 않습니다.

## Endpoints

성공 응답은 모두 `{"success": true, "data": ...}`로 감싸집니다 (`SuccessResponse[T]`).
아래 표기는 `data` 안쪽입니다.

- `GET /health` → `{"status": "ok", "api_key_configured": bool}`
- `GET /styles` → `{key: label}` (`STYLES`에서 생성)
- `POST /translate` — `{text, target_lang, style}` (text ≤ `SHORT_LIMIT` 1,000자, 초과 시 400 `TRANSLATE_ERROR`) → `{candidates: [str, str, str], style}` (서로 다른 후보 3개)
- `POST /translate/long` — 같은 요청 (text ≤ 10,000자) → `{translation: str, style}` (청크별 번역을 이어붙인 결과 1개, 캐시 안 함)

에러는 `services/translate.py`가 `AppError` 하위 예외를 raise하고
`core/error_handlers.py`가 `{"success": false, "error": {"code", "message"}}`로 변환합니다.
서비스 레이어는 FastAPI에 의존하지 않습니다.

| 조건 | status | code |
|---|---|---|
| API 키 미설정 | 500 | `API_KEY_NOT_CONFIGURED` |
| 알 수 없는 스타일 | 400 | `UNKNOWN_STYLE` |
| 빈 텍스트 | 400 | `EMPTY_TEXT` |
| 서비스 요청 오류 (예: `/translate`에 `SHORT_LIMIT` 초과) | 400 | `TRANSLATE_ERROR` (`TranslateError` — 사유는 message로) |
| 요청 횟수 한도 초과 (`/translate`만) | 429 | `RATE_LIMIT_EXCEEDED` (`Retry-After` 헤더 포함) |
| Gemini 호출 실패 / 응답이 요청한 개수의 문자열 배열이 아님 | 502 | `TRANSLATION_ENGINE_ERROR` |
| 요청 스키마 검증 실패 | 422 | `VALIDATION_ERROR` (`RequestValidationError` 핸들러) |
| 그 외 미처리 예외 | 500 | `INTERNAL_ERROR` (원문은 로그로만, 클라이언트엔 비노출) |

## Gemini 호출

`clients/gemini.py` — 모델 `gemini-3.5-flash`, temperature 0.3, max_output_tokens 4096. 비동기 API(`client.aio.models.generate_content`)로 호출합니다.
structured output(`response_mime_type="application/json"`, `response_schema=list[str]`)으로 JSON 문자열 배열을 받고,
`TranslateService._parse_candidates()`가 요청한 후보 개수인지 검증합니다.
형식이 어긋나면 502 전에 `model output malformed: expected=N got=...` warning을 남깁니다 (원소 개수·타입만, 원문 없음).

`translate()`는 호출 1번에 후보 `CANDIDATE_COUNT`(3)개. 한글은 1,000자를 넘으면 후보 3개가 4096 토큰을 넘겨 잘릴 수 있어 `SHORT_LIMIT`로 막습니다.
`translate_long()`은 `chunk_text()`가 문단 → 문장 → 글자 순으로 `CHUNK_SIZE`(2,000자) 이하 청크로 나누고,
청크를 병렬 호출해 1개씩 받아 원문의 구분 공백을 끼워 이어붙입니다 (`"".join(chunks) == text` 불변식).

청크를 따로 번역하면 청크 간 용어와 흐름이 어긋나므로 (#17에서 RAG 대신 택한 방식):

- **용어집 선추출** — 청크가 2개 이상이면 번역 전에 전체 원문으로 `_extract_glossary()`를 1번 호출해
  고유명사·핵심 용어의 번역 규칙(`list[GlossaryTerm]`, 최대 `GLOSSARY_MAX_TERMS`개)을 받고, 모든 청크 시스템 프롬프트에 넣습니다.
  청크가 1개면 생략합니다. **청크 2개 이상이면 Gemini 호출이 1회 늘고, 추출이 끝나야 번역이 시작돼 응답이 그만큼 늦어집니다.**
- **앞 청크 문맥** — 각 청크 시스템 프롬프트에 앞 청크 원문의 마지막 `CONTEXT_TAIL_CHARS`(300)자를 "번역하지 말 것"으로 첨부합니다.
  contents에는 번역할 청크 본문만 둡니다 — 참고 문맥이 사용자 입력에 섞이면 함께 번역될 위험이 큽니다.
- **추출은 fail-open** — API 에러, 출력 잘림, JSON/형식 검증 실패, timeout(`GLOSSARY_TIMEOUT_SECONDS`) 모두
  warning 로그(`glossary extraction failed`)만 남기고 용어집 없이 번역합니다. 로그로 품질 저하 빈도를 확인합니다.
  모든 청크가 추출을 기다리므로 timeout은 번역 호출보다 짧게 잡습니다.
- `GeminiClient.generate()`의 `response_schema` / `max_output_tokens` 키워드는 추출 호출만 넘깁니다 (기본값은 번역용).

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `GLOSSARY_TIMEOUT_SECONDS` | `8` | 용어집 추출 timeout. 넘기면 용어집 없이 번역 |

Gemini 호출과 `APIError` → `TranslationEngineError` 변환은 `_generate()` 한곳에서 합니다.
`GEMINI_API_KEY`가 없으면 `_client=None`이 되고 `is_configured`가 False (import 자체는 성공하므로 CI에서 키 없이 테스트 가능).

프롬프트는 `TranslateService._build_system_prompt()`에서 `target_lang` + 스타일 `description` + few-shot `examples`를 한국어 시스템 지시문에 주입하고, 요청한 개수(3개 또는 1개)를 JSON 배열로 출력하라는 지시로 끝납니다.
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
- "느려질 뿐"이 성립하는 건 `clients/redis_client.py`의 타임아웃(`REDIS_TIMEOUT_SECONDS`, 0.5초) 덕분입니다.
  redis-py 기본값은 무한 대기라, 타임아웃 없이 Redis가 응답하지 않으면 모든 `/translate` 요청이
  끝나지 않습니다. **Redis 클라이언트를 새로 만들지 말고 공용 `redis_client`를 쓰세요.**
- 검증 실패와 Gemini 호출 실패는 캐싱하지 않습니다 (실패를 캐싱하면 TTL 동안 계속 실패).

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `REDIS_URL` | `""` | 비어 있으면 `NullCache` — 캐시 없이 동작 |
| `CACHE_ENABLED` | `true` | `false`면 `REDIS_URL`이 있어도 캐시 끔 |
| `CACHE_TTL_SECONDS` | `3600` | 캐시 항목 만료 시간 |

로컬에서 Redis 없이 개발해도 됩니다. `REDIS_URL`을 비워두면 매번 Gemini를 호출할 뿐입니다.

## Rate Limiting

`POST /translate`만 클라이언트 IP마다 요청 횟수를 제한합니다 (`/health`, `/styles`는 제외).
`POST /translate/long`은 아직 제한이 없습니다 — 청크 수만큼 Gemini를 부르고 캐시도 안 하지만, 적용 여부와 방식(요청당 1회 / 청크 수만큼 차감)은 팀 회의에서 정하기로 함.
라우트의 `dependencies=[Depends(enforce_rate_limit)]`로 걸려 있어 서비스 레이어보다 먼저 실행됩니다.
그래서 한도를 넘긴 요청은 Gemini에 닿지 않고, **캐시 hit도 횟수에 포함됩니다.**

- Redis 고정 윈도우 카운터 — key `ratelimit:{ip}:{윈도우 번호}`에 `INCR` + `EXPIRE`를
  MULTI/EXEC 파이프라인으로 보냅니다. 카운터가 Redis에 있어 여러 프로세스/인스턴스가 한도를 공유합니다.
- 초과 시 `RateLimitExceededError` → 429 + `Retry-After` 헤더. 메시지에도 남은 초가 들어갑니다
  (프론트엔드는 에러 메시지를 그대로 보여주므로 프론트 수정 없이 사용자에게 전달됨).
  응답 헤더가 필요한 예외는 `AppError.headers`에 넣으면 `app_error_handler`가 실어 보냅니다.
- **캐시와 같은 원칙으로 fail-open입니다.** `REDIS_URL`이 없거나 Redis가 죽으면 제한 없이 통과하고
  로그만 남깁니다. rate limiter 장애가 곧 서비스 장애가 되면 안 되기 때문입니다.
- 클라이언트 식별은 `request.client.host`입니다. 프록시 뒤에 배포하면 모든 요청이 프록시 IP로 보이므로
  `X-Forwarded-For` 처리가 필요합니다 (`api/routes.py` 주석 참고).
- 부하 테스트 때는 `RATE_LIMIT_ENABLED=false`로 끄세요. 켜 두면 한 IP에서 보내는 부하가 전부 429로 막힙니다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | `false`면 `REDIS_URL`이 있어도 제한 끔 |
| `RATE_LIMIT_REQUESTS` | `10` | 윈도우당 허용 요청 수 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | 윈도우 길이 |

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
- rate limiter도 마찬가지로 `FakeRateLimiter`가 `client` / `make_client`에 주입됩니다. 기본은
  무제한(`limit=None`)이라 다른 테스트에 영향이 없고, 429를 검증할 때만 `fake_rate_limiter.limit`을 정하세요.
- 대역도 async입니다. `fake.generate`를 바꿔 끼울 때는 `async def`로 정의하세요.
  장문 2청크 이상을 다루면 용어집 추출 호출도 오므로 `**options`를 받으세요.
- `FakeGeminiClient`는 용어집 추출 호출(`response_schema`를 넘김)을 `calls`가 아닌 `glossary_calls`에 기록하고
  `glossary_reply`를 돌려줍니다 (예외를 넣으면 raise). 번역 호출만 세는 테스트가 추출 호출에 영향받지 않습니다.
  `RedisCache` / `RedisRateLimiter` 테스트의 `FakeRedis`도 `redis.asyncio`처럼 `get/set/execute`만 async입니다.
- 엔드포인트 테스트는 `TestClient`가 이벤트 루프를 대신 돌리므로 평범한 `def`로 씁니다.
  서비스나 클라이언트를 직접 `await`하는 테스트만 `@pytest.mark.anyio` + `async def`로 씁니다
  (anyio pytest 플러그인 — FastAPI 의존성으로 설치되어 별도 패키지 불필요).
- `test_requests_wait_for_gemini_concurrently`는 `httpx.AsyncClient`로 요청 여러 개를 동시에 보내,
  Gemini 대기 중 다른 요청이 처리되는지 검증합니다. 이벤트 루프를 막는 코드가 들어오면 타임아웃으로 실패합니다.
