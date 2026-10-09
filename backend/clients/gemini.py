import logging

from google import genai
from google.genai import types as genai_types

from core.config import settings
from core.exceptions import TranslationEngineError

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def generate(
        self,
        contents: str,
        system_instruction: str,
        *,
        response_schema=list[str],
        max_output_tokens: int = 4096,
    ) -> str:
        # 기본값은 번역용(문자열 배열). 용어집 추출은 다른 스키마와 짧은 출력 한도를 넘깁니다.
        # 비동기 API(client.aio)를 씁니다. 동기 API를 async 라우트에서 부르면 응답을 기다리는
        # 수 초 동안 이벤트 루프가 멈춰 다른 요청도 전부 멈춥니다.
        response = await self._client.aio.models.generate_content(
            model=settings.MODEL_NAME,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                response_schema=response_schema,
                thinking_config=genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.LOW),
            ),
        )
        # 운영 로그로 SHORT_LIMIT / CHUNK_SIZE를 조정합니다 (측정 스크립트는 쿼터를 따로 씀).
        # thinking 토큰도 max_output_tokens에 포함됩니다. 원문은 남기지 않습니다.
        usage = response.usage_metadata or genai_types.GenerateContentResponseUsageMetadata()
        finish = response.candidates[0].finish_reason if response.candidates else None
        truncated = finish == genai_types.FinishReason.MAX_TOKENS
        logger.log(
            logging.WARNING if truncated else logging.INFO,
            "gemini usage chars=%d prompt=%s answer=%s thoughts=%s finish=%s",
            len(contents),
            usage.prompt_token_count,
            usage.candidates_token_count,
            usage.thoughts_token_count,
            finish.name if finish else None,
        )
        if truncated:
            raise TranslationEngineError("번역 결과가 너무 길어 잘렸습니다. 글을 나눠서 시도해주세요.")
        return response.text or ""


gemini_client = GeminiClient()
