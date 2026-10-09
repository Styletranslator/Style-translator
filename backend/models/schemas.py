from pydantic import BaseModel, ConfigDict, Field


class TranslateRequest(BaseModel):
    text: str = Field(max_length=10000)
    target_lang: str
    style: str


class TranslateResponse(BaseModel):
    candidates: list[str]
    style: str


class LongTranslateResponse(BaseModel):
    translation: str
    style: str


# 장문 번역 전에 뽑는 용어 번역 규칙. Gemini structured output 스키마 겸 응답 검증용.
# docstring은 스키마 description으로 모델에 그대로 전달되므로 주석으로 둡니다.
class GlossaryTerm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class HealthData(BaseModel):
    status: str
    api_key_configured: bool
