import { useEffect, useState } from 'react'
import './App.css'
import { fetchStyles, MAX_LENGTH } from './api/client'
import { useTranslate } from './hooks/useTranslate'

const FALLBACK_STYLES = {
  general: '일반체',
  formal: '격식체 (해요체)',
  sns: 'SNS체 (대화체)',
}

const LANGUAGES = [
  { code: 'en', label: '영어' },
  { code: 'ko', label: '한국어' },
  { code: 'ja', label: '일본어' },
  { code: 'zh', label: '중국어' },
]

export default function App() {
  const [styles, setStyles] = useState(FALLBACK_STYLES)
  const [text, setText] = useState('')
  const [targetLang, setTargetLang] = useState('en')
  const [style, setStyle] = useState('general')
  const { candidates, selected, setSelected, loading, error, translate } = useTranslate()

  useEffect(() => {
    fetchStyles().then(setStyles).catch(() => {})
  }, [])

  return (
    <div className="page">
      <header className="page__header">
        <span className="eyebrow">STYLE TRANSLATOR — BETA</span>
        <h1>AI Translator</h1>
        <p className="subtitle">문장을 넣고 스타일을 고르면, 그 말투로 다시 바꿔 드립니다.</p>
      </header>

      <main className="panel">
        <textarea
          className="input-area"
          placeholder="문장을 입력하세요"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          maxLength={MAX_LENGTH}
        />

        <div className="controls">
          <div className="control">
            <label htmlFor="lang">언어</label>
            <select id="lang" value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>{lang.label}</option>
              ))}
            </select>
          </div>

          <div className="control">
            <label htmlFor="style">스타일</label>
            <select id="style" value={style} onChange={(e) => setStyle(e.target.value)}>
              {Object.entries(styles).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          <button
            className="translate-btn"
            onClick={() => translate({ text, targetLang, style })}
            disabled={loading}
          >
            {loading ? '변환 중…' : '변환하기'}
          </button>
        </div>

        {error && <p className="error" role="alert">{error}</p>}

        {candidates.length > 0 && (
          <div className="result">
            <span className="result__label">
              결과 · {styles[style] ?? style}
              {candidates.length > 1 && ' · 마음에 드는 번역을 고르세요'}
            </span>
            {candidates.map((candidate, i) => (
              <button
                key={i}
                type="button"
                className="candidate"
                aria-pressed={selected === i}
                onClick={() => setSelected(i)}
              >
                <p className="result__text">{candidate}</p>
              </button>
            ))}
          </div>
        )}
      </main>

      <footer className="page__footer">
        <span>백엔드: FastAPI + Gemini API</span>
      </footer>
    </div>
  )
}
