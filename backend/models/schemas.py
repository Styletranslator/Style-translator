from pydantic import BaseModel, Field


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


class HealthData(BaseModel):
    status: str
    api_key_configured: bool
