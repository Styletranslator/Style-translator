import { useEffect, useState } from 'react'
import { fetchStyles, MAX_LENGTH, SHORT_LIMIT } from './api/client'
import { useTranslate } from './hooks/useTranslate'
import { DEFAULT_LANGUAGE, LANGUAGES } from './constants/languages'
import Header from './components/Header/Header'
import StyleCarousel from './components/StyleCarousel/StyleCarousel'
import InputPanel from './components/InputPanel/InputPanel'
import LangToggle from './components/LangToggle/LangToggle'
import Pill from './components/Pill/Pill'
import PlayButton from './components/PlayButton/PlayButton'
import ResultPanel from './components/ResultPanel/ResultPanel'
// 자식 컴포넌트 CSS 뒤에 들어가야 className 덮어쓰기(styleChip)가 이김
import typography from './styles/typography.module.css'
import styles from './App.module.css'

// /styles 실패 시 사용 — 백엔드 styles.py의 label과 맞춤
const FALLBACK_STYLES = {
  general: '일반체',
  formal: '격식체',
  sns: 'SNS체',
}

export default function App() {
  const [styleMap, setStyleMap] = useState(FALLBACK_STYLES)
  const [text, setText] = useState('')
  const [targetLang, setTargetLang] = useState(DEFAULT_LANGUAGE)
  const [style, setStyle] = useState('general')
  const { candidates, selected, setSelected, result, pending, error, inputHint, translate } = useTranslate()

  useEffect(() => {
    fetchStyles().then(setStyleMap).catch(() => {})
  }, [])

  const isLong = text.length > SHORT_LIMIT
  const isLoadingLong = pending?.isLong ?? false
  // 장문 로딩 중엔 진행 중인 요청, 그 외엔 결과를 만든 요청 기준으로 헤더를 그림
  const shownRequest = isLoadingLong ? pending : result
  const resultInfo = shownRequest && {
    styleLabel: styleMap[shownRequest.style] ?? shownRequest.style,
    languageLabel: LANGUAGES.find((language) => language.code === shownRequest.targetLang)?.label,
    sourceLength: shownRequest.sourceLength,
  }

  function handleTranslate() {
    translate({ text, targetLang, style })
  }

  return (
    <div className={styles.page}>
      <Header />
      <StyleCarousel styles={styleMap} value={style} onChange={setStyle} />
      <main className={styles.main}>
        <InputPanel
          text={text}
          onTextChange={setText}
          onSubmit={handleTranslate}
          hint={inputHint}
          isLong={isLong}
          counterLimit={isLong ? MAX_LENGTH : SHORT_LIMIT}
          maxLength={MAX_LENGTH}
          controls={
            <>
              <LangToggle languages={LANGUAGES} value={targetLang} onChange={setTargetLang} />
              <Pill type="chip" className={styles.styleChip}>{styleMap[style] ?? style}</Pill>
            </>
          }
          action={<PlayButton isLoading={pending !== null} onClick={handleTranslate} />}
        />
        <ResultPanel
          candidates={candidates}
          selected={selected}
          onSelect={setSelected}
          error={error}
          isTranslating={pending !== null}
          isLoadingLong={isLoadingLong}
          info={resultInfo}
        />
      </main>
      <footer className={`${styles.footer} ${typography.uiFooter}`}>© 2026 Style Translator · FastAPI + Gemini API</footer>
    </div>
  )
}
