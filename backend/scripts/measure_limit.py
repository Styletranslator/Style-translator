"""SHORT_LIMIT 측정 — 수동 실행용. 실제 Gemini를 호출합니다.

실행 (backend/에서):  python -m scripts.measure_limit

후보 3개 생성 프롬프트로 4096 토큰 한도에 맞는 입력 길이를 측정해 limit_results.csv에 기록합니다.
모델이나 프롬프트를 바꾸면 다시 돌려 SHORT_LIMIT를 재측정하세요.

1단계: 전 조합을 첫 문단(314자)으로 보내 글자당 출력 토큰 비율 측정
2단계: 비율이 가장 큰 조합으로 이분 탐색 (10자 해상도, 각 길이 3회)
"""
import csv
import itertools
import time
from pathlib import Path

from google import genai
from google.genai import types

from core.config import settings
from services.translate import CANDIDATE_COUNT, TranslateService
from styles import STYLES

HERE = Path(__file__).parent
SAMPLE = HERE / "measure_limit_sample.txt"
RESULTS = HERE / "limit_results.csv"

LANGS = ["en", "ja", "zh"]
N, REPEAT = 314, 1  # 1단계 입력 길이(첫 문단 기준), 조합당 반복 횟수
SLEEP = 8  # 요청 간격(초), 무료 등급 분당 한도 대비

FIELDS = ["phase", "style", "lang", "chars", "prompt_tokens", "candidates_tokens",
          "thoughts_tokens", "out_tokens", "out_per_char", "finish_reason"]


def main():
    assert settings.GEMINI_API_KEY, "backend/.env에 GEMINI_API_KEY가 없습니다."
    sample = SAMPLE.read_text(encoding="utf-8")
    print(f"샘플 {len(sample)}자, 모델 {settings.MODEL_NAME}")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    svc = TranslateService(client=None)  # 프롬프트 조립만 사용

    with RESULTS.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글 안 깨짐
        writer = csv.writer(f)
        writer.writerow(FIELDS)

        def call(phase, text, style, lang):
            r = client.models.generate_content(
                model=settings.MODEL_NAME,
                contents=text,
                config=types.GenerateContentConfig(   # clients/gemini.py와 같은 설정
                    system_instruction=svc._build_system_prompt(lang, STYLES[style], CANDIDATE_COUNT),
                    temperature=0.3,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                    response_schema=list[str],
                    # thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.원하는 레벨)
                ),
            )
            time.sleep(SLEEP)
            u = r.usage_metadata
            cand, thoughts = u.candidates_token_count or 0, u.thoughts_token_count or 0
            out = cand + thoughts  # thinking 토큰도 max_output_tokens에 포함됨
            finish = r.candidates[0].finish_reason
            writer.writerow([phase, style, lang, len(text), u.prompt_token_count, cand, thoughts,
                             out, f"{out / len(text):.3f}", finish.name if finish else ""])
            f.flush()  # 한 건마다 저장 — 쿼터로 중간에 죽어도 보존
            return out, finish == types.FinishReason.MAX_TOKENS

        # 1단계: 비율 측정
        rates = {}
        for style, lang in itertools.product(STYLES, LANGS):
            outs = [call("ratio", sample[:N], style, lang)[0] for _ in range(REPEAT)]
            rates[(style, lang)] = max(outs) / N
            print(style, lang, f"{rates[(style, lang)]:.2f} tok/char")

        worst = max(rates, key=rates.get)
        est = int(4096 / rates[worst])
        print("최악 조합:", worst, "예상 경계:", est)

        # 2단계: 이분 탐색
        def fails(n):
            return any(call("bisect", sample[:n], *worst)[1] for _ in range(3))

        lo, hi = int(est * 0.8), min(int(est * 1.2), len(sample))
        while hi - lo > 10:
            mid = (lo + hi) // 2
            if fails(mid):
                hi = mid
            else:
                lo = mid
    print(f"최악 조합 {worst}: {lo}자 통과, {hi}자 초과")


if __name__ == "__main__":
    main()
