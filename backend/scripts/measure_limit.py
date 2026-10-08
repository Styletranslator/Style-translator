"""SHORT_LIMIT 확인 — 수동 실행용. 실제 Gemini를 호출합니다.

실행 (backend/에서):
  python -m scripts.measure_limit                # 확인만: COMBOS × REPS (기본 9회)
  python -m scripts.measure_limit --find-worst   # 1단계(전 조합 비율 측정) 후 상위 TOP개로 확인

/translate와 같은 조건(후보 3개, max_output_tokens MAX_OUTPUT)으로 TARGET자 입력을 보내,
출력이 한도의 SAFE_RATIO 이하인지 확인합니다. 결과는 실행할 때마다 RESULTS에 새로 씁니다(이전 결과는 지워짐).
모델·프롬프트·thinking 설정을 바꾸면 다시 확인하세요.

1단계는 최악 조합이 바뀌었을 수 있을 때만 쓰세요 (예: 모델이나 thinking 설정 변경).
"""
import argparse
import csv
import itertools
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from core.config import settings
from services.translate import CANDIDATE_COUNT, TranslateService
from styles import STYLES

HERE = Path(__file__).parent
SAMPLE = HERE / "measure_limit_sample.txt"
RESULTS = HERE / "limit_results.csv"     # 실행마다 덮어씀 — 남길 결과는 파일 이름을 바꿔 두기

# ── 설정 ─────────────────────────────────────────────────────────────
TARGET = 1000                                     # 확인할 SHORT_LIMIT 후보
SAFE_RATIO = 0.8                                  # 출력이 한도의 이 비율을 넘으면 '여유 부족'
MAX_OUTPUT = 4096                                 # 운영 max_output_tokens (clients/gemini.py)
THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)  # 확인하고자 하는 thinking 설정
COMBOS = [("formal", "zh"), ("general", "zh"), ("sns", "zh")]  # 지난 측정 상위 3개 (--find-worst면 무시)
REPS = 2                                          # 각 조합 반복 횟수
TOP = 3                                           # --find-worst에서 고를 상위 조합 수
LANGS = ["en", "ja", "zh"]                        # 1단계 대상 언어 (프론트 LANGUAGES 중 ko 제외)
RATIO_CHARS = 314                                 # 1단계 입력 길이 (샘플 첫 문단)
SLEEP = 8                                         # 요청 간격(초), 무료 등급 분당 한도 대비
# ─────────────────────────────────────────────────────────────────────

FIELDS = ["phase", "style", "lang", "chars", "prompt_tokens", "candidates_tokens",
          "thoughts_tokens", "out_tokens", "out_per_char", "finish_reason"]


def make_caller(client, writer, f):
    svc = TranslateService(client=None)  # 프롬프트 조립만 사용

    def call(phase: str, text: str, style: str, lang: str) -> tuple[int, bool]:
        r = client.models.generate_content(
            model=settings.MODEL_NAME,
            contents=text,
            config=types.GenerateContentConfig(   # clients/gemini.py와 같은 설정
                system_instruction=svc._build_system_prompt(lang, STYLES[style], CANDIDATE_COUNT),
                temperature=0.3,
                max_output_tokens=MAX_OUTPUT,
                response_mime_type="application/json",
                response_schema=list[str],
                thinking_config=THINKING,
            ),
        )
        time.sleep(SLEEP)
        u = r.usage_metadata
        cand, thoughts = u.candidates_token_count or 0, u.thoughts_token_count or 0
        out = cand + thoughts  # thinking 토큰도 max_output_tokens에 포함됨
        finish = r.candidates[0].finish_reason if r.candidates else None
        writer.writerow([phase, style, lang, len(text), u.prompt_token_count, cand,
                         thoughts, out, f"{out / len(text):.3f}", finish.name if finish else ""])
        f.flush()  # 한 건마다 저장 — 쿼터로 중간에 죽어도 보존
        return out, finish == types.FinishReason.MAX_TOKENS

    return call


def find_worst(call, sample: str, top: int = TOP) -> list[tuple[str, str]]:
    """1단계: 전 조합을 같은 입력으로 보내 글자당 출력 토큰이 큰 순으로 top개 반환."""
    text = sample[:RATIO_CHARS]
    print(f"\n[1단계] {len(STYLES) * len(LANGS)}개 조합, {len(text)}자")
    rates = {}
    for style, lang in itertools.product(STYLES, LANGS):
        out, truncated = call("ratio", text, style, lang)
        rates[(style, lang)] = float("inf") if truncated else out / len(text)
        print(f"  {style}/{lang}  {rates[(style, lang)]:.2f} tok/char")
    ranked = sorted(rates, key=rates.get, reverse=True)[:top]
    print(f"  → 상위 {top}개: " + ", ".join(f"{s}/{l}" for s, l in ranked))
    return ranked


def verify(call, sample: str, combos: list[tuple[str, str]]) -> None:
    text = sample[:TARGET]
    for style, lang in combos:
        for _ in range(REPS):
            out, truncated = call("verify", text, style, lang)
            status = "초과" if truncated else "여유 부족" if out > MAX_OUTPUT * SAFE_RATIO else "OK"
            print(f"{style}/{lang} {TARGET}자 → {out} tok ({out / MAX_OUTPUT:.0%}) {status}")


def main():
    parser = argparse.ArgumentParser(description="SHORT_LIMIT 확인")
    parser.add_argument("--find-worst", action="store_true",
                        help="전 조합을 먼저 측정해 상위 TOP개로 확인 (+9회)")
    args = parser.parse_args()

    assert settings.GEMINI_API_KEY, "backend/.env에 GEMINI_API_KEY가 없습니다."
    sample = SAMPLE.read_text(encoding="utf-8")
    if len(sample) < TARGET:
        raise SystemExit(f"샘플이 {len(sample)}자 — TARGET({TARGET})보다 길어야 합니다.")
    calls = (len(STYLES) * len(LANGS) + TOP * REPS) if args.find_worst else len(COMBOS) * REPS
    print(f"샘플 {len(sample)}자, 모델 {settings.MODEL_NAME}, 예상 요청 {calls}회")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    with RESULTS.open("w", newline="", encoding="utf-8-sig") as f:  # 실행마다 새로 씀, utf-8-sig: 엑셀 한글
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        call = make_caller(client, writer, f)
        try:
            combos = find_worst(call, sample) if args.find_worst else COMBOS
            verify(call, sample, combos)
        except genai_errors.ClientError as exc:
            if exc.code != 429:
                raise
            print(f"\n429 쿼터 초과 — 받은 결과는 {RESULTS.name}에 저장됨. 한도가 풀리면 다시 실행하세요.")


if __name__ == "__main__":
    main()
