import json

from google.genai import errors as genai_errors

from clients.cache import NullCache, TranslationCache, build_cache_key
from clients.gemini import GeminiClient
from core.exceptions import (
    ApiKeyNotConfiguredError,
    EmptyTextError,
    TranslationEngineError,
    UnknownStyleError,
)
from styles import STYLES

CANDIDATE_COUNT = 3


def _is_valid_candidates(value) -> bool:
    """약속된 형식(비어 있지 않은 문자열 CANDIDATE_COUNT개)인지 확인합니다.

    모델 응답과 캐시에서 꺼낸 값에 같은 기준을 적용하기 위해 분리했습니다.
    """
    return (
        isinstance(value, list)
        and len(value) == CANDIDATE_COUNT
        and all(isinstance(c, str) and c.strip() for c in value)
    )


class TranslateService:
    def __init__(self, client: GeminiClient, cache: TranslationCache | None = None):
        self.client = client
        # 캐시를 넘기지 않으면 항상 miss인 NullCache를 씁니다 — 호출부가 캐시 유무를
        # 분기하지 않아도 되도록.
        self.cache = cache or NullCache()

    def translate(self, text: str, target_lang: str, style: str) -> list[str]:
        if not self.client.is_configured:
            raise ApiKeyNotConfiguredError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        if style not in STYLES:
            raise UnknownStyleError(f"알 수 없는 스타일: {style}")
        if not text.strip():
            raise EmptyTextError("번역할 텍스트가 비어 있습니다.")

        # 검증을 통과한 요청만 캐시를 봅니다 — 잘못된 요청을 캐싱할 이유가 없습니다.
        cache_key = build_cache_key(text, target_lang, style)
        cached = self.cache.get(cache_key)
        # 형식을 확인하고 씁니다 — KEY_PREFIX를 올리지 않은 채 저장 형식이 바뀌어도
        # 옛 값이 그대로 나가지 않고 miss로 처리됩니다.
        if _is_valid_candidates(cached):
            return cached

        style_def = STYLES[style]
        system_prompt = self._build_system_prompt(target_lang, style_def)
        try:
            result = self.client.generate(text, system_prompt)
        except genai_errors.APIError as exc:
            # 업스트림 예외 원문은 로그로만 남김 (exc_info 체이닝) — 내부 정보라 클라이언트엔 비노출.
            raise TranslationEngineError("번역 엔진 호출에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

        # 파싱에 실패하면 여기서 502가 나가고 캐시에는 아무것도 들어가지 않습니다.
        candidates = self._parse_candidates(result)
        self.cache.set(cache_key, candidates)
        return candidates

    def list_styles(self) -> dict:
        return {key: value["label"] for key, value in STYLES.items()}

    def _parse_candidates(self, raw: str) -> list[str]:
        # structured output을 요청해도 형식이 어긋날 수 있으므로 업스트림 오류(502)로 처리.
        message = "번역 결과를 해석하지 못했습니다. 잠시 후 다시 시도해주세요."
        try:
            candidates = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranslationEngineError(message) from exc
        if not _is_valid_candidates(candidates):
            raise TranslationEngineError(message)
        return [c.strip() for c in candidates]

    def _build_system_prompt(self, target_lang: str, style_def: dict) -> str:
        examples = "\n".join(
            f'- 원문: "{ex["source"]}" → 번역: "{ex["target"]}"' for ex in style_def["examples"]
        )
        return (
            f"당신은 전문 번역가입니다. 사용자가 준 텍스트를 '{target_lang}' 언어로 번역하되, "
            f"다음 스타일을 반드시 지키세요.\n\n"
            f"스타일 설명: {style_def['description']}\n\n"
            f"스타일 예시:\n{examples}\n\n"
            f"어휘나 어순이 서로 다른 번역 후보 {CANDIDATE_COUNT}개를 만들고, 모든 후보가 위 스타일을 지키게 하세요. "
            f"후보 {CANDIDATE_COUNT}개를 JSON 문자열 배열로만 출력하세요. 설명이나 부연 설명을 붙이지 마세요."
        )
