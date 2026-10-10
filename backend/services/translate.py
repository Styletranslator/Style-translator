import asyncio
import json
import logging

from google.genai import errors as genai_errors
from pydantic import TypeAdapter, ValidationError

from clients.cache import NullCache, TranslationCache, build_cache_key
from clients.gemini import GeminiClient
from core.config import settings
from core.exceptions import (
    ApiKeyNotConfiguredError,
    EmptyTextError,
    TranslateError,
    TranslationEngineError,
    UnknownStyleError,
)
from models.schemas import GlossaryTerm
from services.chunking import chunk_text
from styles import STYLES

logger = logging.getLogger(__name__)

CANDIDATE_COUNT = 3
# 한글 기준 후보 3개 × max_output_tokens 4096 안에 들어가는 입력 크기 (/translate 상한).
SHORT_LIMIT = 1000
# 장문 번역 — 각 청크에 참고용으로 붙이는 앞 청크 원문의 꼬리 길이.
CONTEXT_TAIL_CHARS = 300
# 용어집이 길면 모든 청크 프롬프트가 함께 길어지므로 개수 제한
GLOSSARY_MAX_TERMS = 30
# 용어집 추출용 토큰 한도 
GLOSSARY_MAX_OUTPUT_TOKENS = 2048

_glossary_adapter = TypeAdapter(list[GlossaryTerm])


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
        """장문 — 청크마다 번역 1개를 받아 원문의 구분 공백을 끼워 이어붙임. 캐시하지 않음.

        청크를 병렬로 번역하므로, 청크 간 용어와 흐름이 어긋나지 않도록
        전체 원문에서 뽑은 용어집과 앞 청크 원문의 꼬리를 각 청크 프롬프트에 넣습니다.
        """
        style_def = self._validate(text, style)
        chunks = chunk_text(text)
        bodies = [chunk.strip() for chunk in chunks]

        glossary = await self._extract_glossary(text, target_lang) if sum(map(bool, bodies)) > 1 else []

        jobs = []
        previous = ""
        for body in bodies:
            if body:
                prompt = self._build_system_prompt(
                    target_lang, style_def, 1, glossary=glossary, context=previous[-CONTEXT_TAIL_CHARS:]
                )
                jobs.append(asyncio.create_task(self._translate_chunk(body, prompt)))
                previous = body
        try:
            translations = iter(await asyncio.gather(*jobs))
        except Exception:
            # 청크 하나라도 실패하면 결과는 502. 쿼터 낭비 방지를 위해 나머지 청크 번역은 취소
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            raise

        parts = []
        for chunk, body in zip(chunks, bodies):
            if body:
                parts.append(next(translations))
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

    async def _translate_chunk(self, body: str, system_prompt: str) -> str:
        return self._parse_candidates(await self._generate(body, system_prompt), 1)[0]

    async def _extract_glossary(self, text: str, target_lang: str) -> list[GlossaryTerm]:
        """전체 원문에서 고유명사·핵심 용어의 번역 규칙을 뽑습니다.

        용어집은 품질 보강일 뿐이라 fail-open입니다 — 어떤 이유로 실패해도 빈 용어집으로
        번역을 이어갑니다. 실패 빈도를 확인할 수 있도록 warning을 남깁니다 (원문은 남기지 않음).
        """
        try:
            raw = await asyncio.wait_for(
                self.client.generate(
                    text,
                    self._build_glossary_prompt(target_lang),
                    response_schema=list[GlossaryTerm],
                    max_output_tokens=GLOSSARY_MAX_OUTPUT_TOKENS,
                ),
                timeout=settings.GLOSSARY_TIMEOUT_SECONDS,
            )
            # 잘못된 JSON과 형식 불일치 모두 ValidationError
            return _glossary_adapter.validate_json(raw)[:GLOSSARY_MAX_TERMS]
        except (genai_errors.APIError, TranslationEngineError, ValidationError, TimeoutError) as exc:
            logger.warning("glossary extraction failed, translating without it: %s", type(exc).__name__)
            return []

    def _parse_candidates(self, raw: str, count: int) -> list[str]:
        # structured output을 요청해도 형식이 어긋날 수 있으므로 업스트림 오류(502)로 처리.
        message = "번역 결과를 해석하지 못했습니다. 잠시 후 다시 시도해주세요."
        try:
            candidates = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("model output malformed: expected=%d got=invalid-json", count)
            raise TranslationEngineError(message) from exc
        if not _is_valid_candidates(candidates, count):
            # 확률적 오류 발생 지점 - /translate/long(zh)에서 청크 응답이 여기(또는 위 JSON 파싱)에 걸려 502가 나간 적이 있어 로깅 추적
            got = f"list[{len(candidates)}]" if isinstance(candidates, list) else type(candidates).__name__
            logger.warning("model output malformed: expected=%d got=%s", count, got)
            raise TranslationEngineError(message)
        return [c.strip() for c in candidates]

    def _build_glossary_prompt(self, target_lang: str) -> str:
        return (
            f"당신은 번역 준비를 돕는 용어 담당자입니다. 사용자가 준 글 전체에서 고유명사(인명, 지명, "
            f"조직·제품·작품명 등)와 글에서 반복되는 핵심 용어를 골라, '{target_lang}' 언어로 옮길 때 "
            f"쓸 표기를 하나씩 정하세요. 흔한 일반 단어는 빼고 최대 {GLOSSARY_MAX_TERMS}개까지, "
            f"원문 표기(source)와 번역 표기(target)의 JSON 배열로만 출력하세요. 해당하는 용어가 없으면 빈 배열을 출력하세요."
        )

    def _build_system_prompt(
        self,
        target_lang: str,
        style_def: dict,
        count: int,
        *,
        glossary: list[GlossaryTerm] = (),
        context: str = "",
    ) -> str:
        examples = "\n".join(
            f'- 원문: "{ex["source"]}" → 번역: "{ex["target"]}"' for ex in style_def["examples"]
        )
        if count == 1:
            output = (
                "번역 결과를 문자열 1개만 담은 JSON 배열로 출력하세요. 문단이 여러 개여도 나누지 말고, "
                "원문의 줄바꿈을 그대로 유지해 하나의 문자열에 담으세요. 설명이나 부연 설명을 붙이지 마세요."
            )
        else:
            output = (
                f"어휘나 어순이 서로 다른 번역 후보 {count}개를 만들고, 모든 후보가 위 스타일을 지키게 하세요. "
                f"후보 {count}개를 JSON 문자열 배열로만 출력하세요. 설명이나 부연 설명을 붙이지 마세요."
            )
        sections = [
            f"당신은 전문 번역가입니다. 사용자가 준 텍스트를 '{target_lang}' 언어로 번역하되, "
            f"다음 스타일을 반드시 지키세요.",
            f"스타일 설명: {style_def['description']}",
            f"스타일 예시:\n{examples}",
        ]
        if glossary:
            terms = "\n".join(f"- {term.source} → {term.target}" for term in glossary)
            sections.append(f"용어집 — 아래 용어가 나오면 반드시 이 번역을 쓰세요:\n{terms}")
        if context:
            # 참고 문맥 — 사용자 입력과 섞이면 함께 번역될 위험
            sections.append(
                "참고용 앞 문맥 — 사용자가 준 텍스트 바로 앞에 오는 원문입니다. 흐름과 지칭을 맞추는 데만 쓰고, "
                "번역하거나 출력에 포함하지 마세요. 출력에는 사용자가 준 텍스트의 번역만 담으세요.\n"
                f'"""\n{context}\n"""'
            )
        sections.append(output)
        return "\n\n".join(sections)
