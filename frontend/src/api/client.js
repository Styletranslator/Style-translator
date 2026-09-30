const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
// 백엔드 SHORT_LIMIT(services/translate.py)와 같아야 함 — 넘으면 장문 엔드포인트로 보냅니다.
export const SHORT_LIMIT = 1000
export const MAX_LENGTH = 10000

// 백엔드는 모든 응답을 { success, data } / { success, error: { code, message } }로 감싸서 보냅니다.
// 이 함수가 그 껍데기를 벗겨내므로, 이 파일 밖에서는 응답 형식을 몰라도 됩니다.
async function unwrap(res, fallbackMessage) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const error = new Error(body.error?.message || fallbackMessage)
    error.code = body.error?.code
    throw error
  }
  const body = await res.json()
  return body.data
}

export async function fetchStyles() {
  const res = await fetch(`${API_BASE}/styles`)
  return unwrap(res, '스타일 목록을 불러오지 못했습니다.')
}

export async function fetchTranslation({ text, targetLang, style }) {
  const isLong = text.length > SHORT_LIMIT
  const res = await fetch(`${API_BASE}/translate${isLong ? '/long' : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, target_lang: targetLang, style }),
  })
  const data = await unwrap(res, '번역 요청이 실패했습니다.')
  // 장문 응답 {translation}을 짧은 응답과 같은 {candidates} 형태로 맞춤 — 훅/화면은 형태를 몰라도 됨.
  return isLong ? { candidates: [data.translation], style: data.style } : data
}
