import { useState } from 'react'
import { fetchTranslation, SHORT_LIMIT } from '../api/client'

export function useTranslate() {
  const [candidates, setCandidates] = useState([])
  const [selected, setSelected] = useState(0)
  // 결과 헤더·정보 줄은 화면의 현재 선택이 아니라 요청 당시 값을 보여줘야 해서 요청 정보를 따로 둠.
  const [result, setResult] = useState(null)
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [inputHint, setInputHint] = useState('')

  async function translate({ text, targetLang, style }) {
    if (!text.trim()) {
      setInputHint('번역할 문장을 입력해 주세요.')
      return
    }
    const request = { style, targetLang, sourceLength: text.length, isLong: text.length > SHORT_LIMIT }
    setPending(request)
    setInputHint('')
    setError('')
    try {
      const data = await fetchTranslation({ text, targetLang, style })
      setCandidates(data.candidates)
      setSelected(0)
      setResult(request)
    } catch (err) {
      setCandidates([])
      setResult(null)
      // fetch 자체가 실패하면(서버 꺼짐, CORS) 브라우저 영문 메시지라 대신 안내 문구를 씀.
      setError(err instanceof TypeError ? '서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.' : err.message)
    } finally {
      setPending(null)
    }
  }

  return {
    candidates,
    selected,
    setSelected,
    result,
    pending,
    error,
    inputHint,
    translate,
  }
}
