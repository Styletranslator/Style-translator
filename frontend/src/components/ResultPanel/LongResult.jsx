import { useState } from 'react'
import Pill from '../Pill/Pill'
import typography from '../../styles/typography.module.css'
import styles from './ResultPanel.module.css'

const COPIED_RESET_MS = 2000

export default function LongResult({ text, info }) {
  const [copyStatus, setCopyStatus] = useState('')

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopyStatus('복사했어요')
    } catch {
      setCopyStatus('복사하지 못했어요')
    }
    setTimeout(() => setCopyStatus(''), COPIED_RESET_MS)
  }

  return (
    <>
      <div className={`${styles.header} ${typography.monoLabel}`}>
        <span>결과 · {info.styleLabel} · 장문</span>
        <Pill className={styles.copyButton} aria-label="번역 복사" onClick={handleCopy}>
          {copyStatus || '복사'}
        </Pill>
        <span className={styles.visuallyHidden} aria-live="polite">{copyStatus}</span>
      </div>
      <div className={styles.longBody}>
        <p className={`${styles.longText} ${typography.bodyLongform}`}>{text}</p>
        <p className={`${styles.longInfo} ${typography.monoLabel}`}>
          원문 {info.sourceLength.toLocaleString()}자 → {info.languageLabel} · {info.styleLabel}
        </p>
      </div>
    </>
  )
}
