import re

# 장문(/translate/long) 청크 크기 — 청크당 1개만 받으므로 SHORT_LIMIT보다 크게 잡아도 여유 있음 (SHORT_LIMIT: services/translate.py).
CHUNK_SIZE = 2000


def chunk_text(text: str, limit: int = CHUNK_SIZE) -> list[str]:
    """문단 → 문장 → 글자 순으로 나눠 limit 이하 청크로 묶습니다.

    구분 공백을 청크 끝에 그대로 남기므로 "".join(chunks) == text 가 성립합니다.
    번역 결과를 이어붙일 때 이 공백을 다시 붙여 문단 구조를 유지합니다.
    """
    units = []
    for para in re.findall(r".+?(?:\n\s*\n|\Z)", text, re.S):
        if len(para) <= limit:
            units.append(para)
            continue
        for sent in re.findall(r".+?(?:[.!?。]\s+|\Z)", para, re.S):
            units += [sent[i : i + limit] for i in range(0, len(sent), limit)]

    chunks: list[str] = []
    for unit in units:
        if chunks and len(chunks[-1]) + len(unit) <= limit:
            chunks[-1] += unit
        else:
            chunks.append(unit)
    return chunks
