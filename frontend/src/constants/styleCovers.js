// 스타일 카드 커버 — 백엔드가 모르는 프론트 전용 표현.
// 커버 색은 CSS가 data-style 속성으로 --color-cover-{key} 토큰을 고릅니다.
export const STYLE_COVERS = {
  general: { glyph: 'Aa', description: '담백하게' },
  formal: { glyph: 'Re:', description: '정중하게' },
  sns: { glyph: 'ㅋㅋ', description: '대화체 · 가볍게' },
}

// 백엔드 styles.py에 스타일이 추가돼도 카드가 깨지지 않도록 key·label로 커버를 만듦.
export function getCover(key, label) {
  return STYLE_COVERS[key] ?? { glyph: key.charAt(0).toUpperCase(), description: label }
}
