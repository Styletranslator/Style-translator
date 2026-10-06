"""thinking 설정 변경 전후 번역 품질 비교 — 수동 실행용. 실제 Gemini를 호출합니다.

실행 (backend/에서):  python -m scripts.eval_thinking

eval_thinking_sample.json의 각 케이스를 CONFIGS의 설정마다 1회씩 /translate와 같은 조건(후보 3개)으로 보내고,
결과를 eval_results.csv에 한 줄씩 쌓습니다. 같은 케이스의 설정별 결과가 연달아 기록되므로
엑셀에서 위아래로 비교하면 됩니다. judgment 칸은 비워 두었으니 읽으면서 채우세요.

- 앱 서버·캐시를 거치지 않고 Gemini를 직접 호출하므로 캐시 설정과 무관합니다.
- 429로 멈추면 같은 명령으로 이어서 진행되고, 이미 기록된 결과는 다시 요청하지 않습니다.
  설정을 바꿔 처음부터 비교하려면 CSV를 지우세요.
"""
import csv
import json
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from core.config import settings
from services.translate import CANDIDATE_COUNT, TranslateService
from styles import STYLES

HERE = Path(__file__).parent
EVAL_SET = HERE / "eval_thinking_sample.json"
RESULTS = HERE / "eval_results.csv"

# ▶ thinking 레벨을 바꿔 테스트하려면 여기만 고치세요.
#   키 = CSV config 칸에 찍히는 이름, 값 = ThinkingConfig (None = 운영과 동일, clients/gemini.py에 thinking 설정 없음)
#   예) "thinking HIGH": types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH),
CONFIGS = {
    "기존": None,
    "thinking LOW": types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
}
SLEEP = 8  # 요청 간격(초), 무료 등급 분당 한도 대비

FIELDS = ["case_id", "type", "style", "lang", "config", "source", "check",
          *[f"candidate_{i + 1}" for i in range(CANDIDATE_COUNT)],
          "candidates_tokens", "thoughts_tokens", "finish", "judgment"]


def load_cases() -> list[dict]:
    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    return [
        {"case_id": f'{item["id"]}:{c["style"]}/{c["lang"]}', "type": item["type"],
         "style": c["style"], "lang": c["lang"], "source": item["text"], "check": item["check"]}
        for item in data["items"] for c in item["cases"]
    ]


def done_keys() -> set[tuple[str, str]]:
    if not RESULTS.exists():
        return set()
    with RESULTS.open(encoding="utf-8-sig") as f:
        return {(r["case_id"], r["config"]) for r in csv.DictReader(f)}


def parse(raw: str) -> list[str] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) and all(isinstance(c, str) for c in value) else None


def main():
    assert settings.GEMINI_API_KEY, "backend/.env에 GEMINI_API_KEY가 없습니다."
    cases = load_cases()
    done = done_keys()
    todo = [(c, n) for c in cases for n in CONFIGS if (c["case_id"], n) not in done]
    print(f"케이스 {len(cases)}개 × 설정 {len(CONFIGS)}개, 남은 요청 {len(todo)}회")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    svc = TranslateService(client=None)  # 프롬프트 조립만 사용
    new_file = not RESULTS.exists()
    sent = 0
    with RESULTS.open("a", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글 안 깨짐
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        try:
            for case, name in todo:
                print(f"  {case['case_id']} [{name}] ...", end=" ", flush=True)
                r = client.models.generate_content(
                    model=settings.MODEL_NAME,
                    contents=case["source"],
                    config=types.GenerateContentConfig(   # clients/gemini.py와 같은 설정 + thinking만 다름
                        system_instruction=svc._build_system_prompt(
                            case["lang"], STYLES[case["style"]], CANDIDATE_COUNT),
                        temperature=0.3,
                        max_output_tokens=4096,
                        response_mime_type="application/json",
                        response_schema=list[str],
                        thinking_config=CONFIGS[name],
                    ),
                )
                sent += 1
                u = r.usage_metadata
                finish = r.candidates[0].finish_reason if r.candidates else None
                raw = r.text or ""
                cands = parse(raw)
                if cands is None:  # 형식이 깨진 응답은 원문 그대로 첫 칸에
                    cands = [f"형식 오류: {raw}"]
                row = {**case, "config": name,
                       "candidates_tokens": u.candidates_token_count or 0,
                       "thoughts_tokens": u.thoughts_token_count or 0,
                       "finish": finish.name if finish else "", "judgment": ""}
                for i in range(CANDIDATE_COUNT):
                    row[f"candidate_{i + 1}"] = cands[i] if i < len(cands) else ""
                writer.writerow(row)
                f.flush()  # 한 건마다 저장 — 중간에 멈춰도 보존
                print(f'번역 {row["candidates_tokens"]} / thinking {row["thoughts_tokens"]} tok')
                time.sleep(SLEEP)
        except genai_errors.ClientError as exc:
            if exc.code != 429:
                raise
            print("\n429 쿼터 초과 — 받은 결과까지 저장됨. 한도가 풀리면 같은 명령으로 이어서 진행하세요.")
    print(f"이번 실행 요청 {sent}회 → {RESULTS.name}")


if __name__ == "__main__":
    main()
