from google import genai
from google.genai import types as genai_types

from core.config import settings


class GeminiClient:
    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    async def generate(self, contents: str, system_instruction: str) -> str:
        # 비동기 API(client.aio)를 씁니다. 동기 API를 async 라우트에서 부르면 응답을 기다리는
        # 수 초 동안 이벤트 루프가 멈춰 다른 요청도 전부 멈춥니다.
        response = await self._client.aio.models.generate_content(
            model=settings.MODEL_NAME,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
                max_output_tokens=4096,
                response_mime_type="application/json",
                response_schema=list[str],
            ),
        )
        return response.text or ""


gemini_client = GeminiClient()
