# scripts/measure_limit.py — 수동 실행용 (backend/에서: python scripts/measure_limit.py)
# 목적: 모델이나 프롬프트를 바꾸면 다시 돌려 SHORT_LIMIT 재측정 필요
# 후보 3개 생성 프롬프트로 4096 토큰 한도에 맞는 입력 길이를 측정
import csv, itertools, time
from pathlib import Path

HERE = Path(__file__).parent

from google import genai
from google.genai import types
from core.config import settings
from services.translate import CANDIDATE_COUNT, TranslateService
from styles import STYLES as STYLE_DEFS

assert settings.GEMINI_API_KEY, "backend/.env에 GEMINI_API_KEY가 없습니다."
client = genai.Client(api_key=settings.GEMINI_API_KEY)
_svc = TranslateService(client=None)  # 프롬프트 조립만 사용, 호출 안 함


def build_system_prompt(lang, style):
    # 운영(/translate)과 같은 system prompt — 후보 CANDIDATE_COUNT개
    return _svc._build_system_prompt(lang, STYLE_DEFS[style], CANDIDATE_COUNT)


STYLES = list(STYLE_DEFS)            # general / formal / sns
LANGS = ["en", "ja", "zh"]
SAMPLE = (HERE / "sample_ko.txt").read_text(encoding="utf-8")
SLEEP = 6   # 무료 등급 RPM에 맞게 조정
print(f"샘플 {len(SAMPLE)}자, 모델 {settings.MODEL_NAME}")

out_file = open(HERE / "results.csv", "w", newline="", encoding="utf-8-sig")  # utf-8-sig: 엑셀에서 한글 안 깨짐
writer = csv.writer(out_file)
writer.writerow(["phase", "style", "lang", "chars", "prompt_tokens", "candidates_tokens",
                 "thoughts_tokens", "out_tokens", "out_per_char", "finish_reason"])
phase = "ratio"


def call(text, style, lang):
    r = client.models.generate_content(
        model=settings.MODEL_NAME,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=build_system_prompt(lang, style),
            temperature=0.3,
            max_output_tokens=4096,          # 운영 설정 그대로 (clients/gemini.py)
            response_mime_type="application/json",
            response_schema=list[str],
        ),
    )
    time.sleep(SLEEP)
    u = r.usage_metadata
    cand, thoughts = u.candidates_token_count or 0, u.thoughts_token_count or 0
    out = cand + thoughts  # thinking 토큰도 max_output_tokens에 포함됨
    finish = r.candidates[0].finish_reason
    writer.writerow([phase, style, lang, len(text), u.prompt_token_count, cand, thoughts,
                     out, f"{out / len(text):.3f}", finish.name if finish else ""])
    out_file.flush()  # 쿼터로 중간에 죽어도 데이터 보존
    return out, finish == types.FinishReason.MAX_TOKENS

# 1단계: 전 조합 314(첫 문단 기준)자로 비율 측정
N, REPEAT = 314, 1
rates = {}
for style, lang in itertools.product(STYLES, LANGS):
    outs = [call(SAMPLE[:N], style, lang)[0] for _ in range(REPEAT)]
    rates[(style, lang)] = max(outs) / N
    print(style, lang, f"{rates[(style, lang)]:.2f} tok/char")

worst = max(rates, key=rates.get)
est = int(4096 / rates[worst])
print("최악 조합:", worst, "예상 경계:", est)

# 2단계: 최악 조합으로 이분 탐색 (10자 해상도, 각 길이 3회)
phase = "bisect"
def fails(n):
    return any(call(SAMPLE[:n], *worst)[1] for _ in range(3))

lo, hi = int(est * 0.8), min(int(est * 1.2), len(SAMPLE))
while hi - lo > 10:
    mid = (lo + hi) // 2
    if fails(mid):
        hi = mid
    else:
        lo = mid
print(f"최악 조합 {worst}: {lo}자 통과, {hi}자 초과")
out_file.close()
