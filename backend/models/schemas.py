from pydantic import BaseModel, Field

from services.translate import SHORT_LIMIT


class TranslateRequest(BaseModel):
    text: str = Field(max_length=SHORT_LIMIT)
    target_lang: str
    style: str


class TranslateResponse(BaseModel):
    candidates: list[str]
    style: str


class LongTranslateRequest(TranslateRequest):
    text: str = Field(max_length=10000)


class LongTranslateResponse(BaseModel):
    translation: str
    style: str


class HealthData(BaseModel):
    status: str
    api_key_configured: bool
