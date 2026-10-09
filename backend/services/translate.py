import json

from google.genai import errors as genai_errors

from clients.cache import NullCache, TranslationCache, build_cache_key
from clients.gemini import GeminiClient
from core.exceptions import (
    ApiKeyNotConfiguredError,
    EmptyTextError,
    TranslateError,
    TranslationEngineError,
    UnknownStyleError,
)
from services.chunking import chunk_text
from styles import STYLES

CANDIDATE_COUNT = 3
# 한글 기준 후보 3개 × max_output_tokens 4096 안에 들어가는 입력 크기 (/translate 상한).
SHORT_LIMIT = 1000


def _is_valid_candidates(value, count: int) -> bool:
    """약속된 형식(비어 있지 않은 문자열 count개)인지 확인합니다.

    모델 응답과 캐시에서 꺼낸 값에 같은 기준을 적용하기 위해 분리했습니다.
    """
    return (
        isinstance(value, list)
        and len(value) == count
        and all(isinstance(c, str) and c.strip() for c in value)
    )


class TranslateService:
    def __init__(self, client: GeminiClient, cache: TranslationCache | None = None):
        self.client = client
        # 캐시를 넘기지 않으면 항상 miss인 NullCache를 씁니다 — 호출부가 캐시 유무를
        # 분기하지 않아도 되도록.
        self.cache = cache or NullCache()

    async def translate(self, text: str, target_lang: str, style: str) -> list[str]:
        """짧은 입력 — 호출 1번에 서로 다른 후보 CANDIDATE_COUNT개."""
        style_def = self._validate(text, style)
        if len(text) > SHORT_LIMIT:
            raise TranslateError(f"{SHORT_LIMIT}자를 넘는 글은 장문 번역(/translate/long)을 사용하세요.")

        # 검증을 통과한 요청만 캐시를 봅니다 — 잘못된 요청을 캐싱할 이유가 없습니다.
        cache_key = build_cache_key(text, target_lang, style)
        cached = await self.cache.get(cache_key)
        # 형식을 확인하고 씁니다 — KEY_PREFIX를 올리지 않은 채 저장 형식이 바뀌어도
        # 옛 값이 그대로 나가지 않고 miss로 처리됩니다.
        if _is_valid_candidates(cached, CANDIDATE_COUNT):
            return cached

        system_prompt = self._build_system_prompt(target_lang, style_def, CANDIDATE_COUNT)
        # 파싱에 실패하면 여기서 502가 나가고 캐시에는 아무것도 들어가지 않습니다.
        candidates = self._parse_candidates(await self._generate(text, system_prompt), CANDIDATE_COUNT)
        await self.cache.set(cache_key, candidates)
        return candidates

    async def translate_long(self, text: str, target_lang: str, style: str) -> str:
        """장문 — 청크마다 번역 1개를 받아 원문의 구분 공백을 끼워 이어붙임. 캐시하지 않음."""
        style_def = self._validate(text, style)
        system_prompt = self._build_system_prompt(target_lang, style_def, 1)
        # 주의사항: 순차 호출 — 청크 수만큼 응답 시간이 늘어남. 느리면 병렬 호출로.
        parts = []
        for chunk in chunk_text(text):
            body = chunk.strip()
            if body:
                parts.append(self._parse_candidates(await self._generate(body, system_prompt), 1)[0])
            parts.append(chunk[len(chunk.rstrip()) :])  # 원문의 문단/문장 구분 공백 보존
        return "".join(parts).strip()

    def list_styles(self) -> dict:
        return {key: value["label"] for key, value in STYLES.items()}

    def _validate(self, text: str, style: str) -> dict:
        if not self.client.is_configured:
            raise ApiKeyNotConfiguredError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        if style not in STYLES:
            raise UnknownStyleError(f"알 수 없는 스타일: {style}")
        if not text.strip():
            raise EmptyTextError("번역할 텍스트가 비어 있습니다.")
        return STYLES[style]

    async def _generate(self, text: str, system_prompt: str) -> str:
        try:
            return await self.client.generate(text, system_prompt)
        except genai_errors.APIError as exc:
            raise TranslationEngineError("번역 엔진 호출에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    def _parse_candidates(self, raw: str, count: int) -> list[str]:
        # structured output을 요청해도 형식이 어긋날 수 있으므로 업스트림 오류(502)로 처리.
        message = "번역 결과를 해석하지 못했습니다. 잠시 후 다시 시도해주세요."
        try:
            candidates = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranslationEngineError(message) from exc
        if not _is_valid_candidates(candidates, count):
            raise TranslationEngineError(message)
        return [c.strip() for c in candidates]

    def _build_system_prompt(self, target_lang: str, style_def: dict, count: int) -> str:
        examples = "\n".join(
            f'- 원문: "{ex["source"]}" → 번역: "{ex["target"]}"' for ex in style_def["examples"]
        )
        if count == 1:
            output = "번역 결과 1개를 JSON 문자열 배열로만 출력하세요. 설명이나 부연 설명을 붙이지 마세요."
        else:
            output = (
                f"어휘나 어순이 서로 다른 번역 후보 {count}개를 만들고, 모든 후보가 위 스타일을 지키게 하세요. "
                f"후보 {count}개를 JSON 문자열 배열로만 출력하세요. 설명이나 부연 설명을 붙이지 마세요."
            )
        return (
            f"당신은 전문 번역가입니다. 사용자가 준 텍스트를 '{target_lang}' 언어로 번역하되, "
            f"다음 스타일을 반드시 지키세요.\n\n"
            f"스타일 설명: {style_def['description']}\n\n"
            f"스타일 예시:\n{examples}\n\n"
            f"{output}"
        )
