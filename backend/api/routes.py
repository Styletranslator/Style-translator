from fastapi import APIRouter, Depends

from clients.cache import translation_cache
from clients.gemini import gemini_client
from core.envelope import SuccessResponse
from models.schemas import HealthData, TranslateRequest, TranslateResponse
from services.translate import TranslateService

router = APIRouter()


def get_translate_service() -> TranslateService:
    return TranslateService(gemini_client, translation_cache)


@router.get("/health", response_model=SuccessResponse[HealthData])
def health_check():
    data = HealthData(status="ok", api_key_configured=gemini_client.is_configured)
    return SuccessResponse(data=data)


@router.get("/styles", response_model=SuccessResponse[dict[str, str]])
def list_styles(service: TranslateService = Depends(get_translate_service)):
    return SuccessResponse(data=service.list_styles())


@router.post("/translate", response_model=SuccessResponse[TranslateResponse])
def translate(req: TranslateRequest, service: TranslateService = Depends(get_translate_service)):
    candidates = service.translate(req.text, req.target_lang, req.style)
    data = TranslateResponse(candidates=candidates, style=req.style)
    return SuccessResponse(data=data)
