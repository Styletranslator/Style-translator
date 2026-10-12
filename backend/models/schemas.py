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


class GlossaryTerm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class HealthData(BaseModel):
    status: str
    api_key_configured: bool
