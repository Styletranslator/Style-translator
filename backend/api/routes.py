from fastapi import APIRouter, Depends, Request

from clients.cache import translation_cache
from clients.gemini import gemini_client
from clients.rate_limiter import RateLimiter, rate_limiter
from core.envelope import SuccessResponse
from core.exceptions import RateLimitExceededError
from models.schemas import (
    HealthData,
    LongTranslateResponse,
    TranslateRequest,
    TranslateResponse,
)
from services.translate import TranslateService

router = APIRouter()


def get_translate_service() -> TranslateService:
    return TranslateService(gemini_client, translation_cache)


def get_rate_limiter() -> RateLimiter:
    return rate_limiter


def enforce_rate_limit(request: Request, limiter: RateLimiter = Depends(get_rate_limiter)) -> None:
    # 주의: 프록시 뒤에 배포하면 모든 요청이 프록시 IP로 보여 한도를 함께 쓰게 됨.
    # 배포 환경이 정해지면 X-Forwarded-For(신뢰하는 프록시가 붙인 것만) 처리를 추가.
    client_id = request.client.host if request.client else "unknown"
    retry_after = limiter.hit(client_id)
    if retry_after is not None:
        raise RateLimitExceededError(
            f"요청이 너무 많습니다. {retry_after}초 후 다시 시도해주세요.", retry_after
        )


@router.get("/health", response_model=SuccessResponse[HealthData])
def health_check():
    data = HealthData(status="ok", api_key_configured=gemini_client.is_configured)
    return SuccessResponse(data=data)


@router.get("/styles", response_model=SuccessResponse[dict[str, str]])
def list_styles(service: TranslateService = Depends(get_translate_service)):
    return SuccessResponse(data=service.list_styles())


# Gemini를 호출하는 엔드포인트에만 제한을 겁니다. 캐시 hit도 횟수에 포함됩니다 —
# 제한은 서비스 레이어(캐시 조회)보다 앞에서 걸리기 때문입니다.
@router.post(
    "/translate",
    response_model=SuccessResponse[TranslateResponse],
    dependencies=[Depends(enforce_rate_limit)],
)
def translate(req: TranslateRequest, service: TranslateService = Depends(get_translate_service)):
    candidates = service.translate(req.text, req.target_lang, req.style)
    data = TranslateResponse(candidates=candidates, style=req.style)
    return SuccessResponse(data=data)


@router.post("/translate/long", response_model=SuccessResponse[LongTranslateResponse])
def translate_long(req: TranslateRequest, service: TranslateService = Depends(get_translate_service)):
    translation = service.translate_long(req.text, req.target_lang, req.style)
    data = LongTranslateResponse(translation=translation, style=req.style)
    return SuccessResponse(data=data)
