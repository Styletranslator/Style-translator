import { useId } from 'react'
import Badge from '../Badge/Badge'
import typography from '../../styles/typography.module.css'
import styles from './InputPanel.module.css'

// controls(언어 토글·스타일 chip)와 action(▶)은 App이 조립해 넘김 — 패널은 배치와 원문 입력만 책임.
export default function InputPanel({ text, onTextChange, onSubmit, hint, isLong, counterLimit, maxLength, controls, action }) {
  const textareaId = useId()
  const counter = `${text.length.toLocaleString()} / ${counterLimit.toLocaleString()}`

  function handleKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <section className={styles.panel} data-long={isLong}>
      <div className={`${styles.labelRow} ${typography.monoLabel}`}>
        <label htmlFor={textareaId}>원문</label>
        {isLong && (
          <>
            <span className={styles.longNotice}>1,000자를 넘어 장문 모드로 번역돼요 · 후보 대신 전체 번역 1개</span>
            <span className={styles.longCounter}>장문 모드 · {counter}</span>
          </>
        )}
      </div>
      <textarea
        id={textareaId}
        className={`${styles.source} ${typography.bodySource}`}
        placeholder="번역할 문장을 입력하세요"
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        maxLength={maxLength}
      />
      {hint && <p className={`${styles.hint} ${typography.cardSub}`} role="alert">{hint}</p>}
      <div className={styles.controls}>
        <span className={`${styles.controlLabel} ${typography.cardSub}`}>도착 언어</span>
        {controls}
        {isLong && <Badge tone="accent" className={styles.longBadge}>장문 모드</Badge>}
        <span className={`${styles.counter} ${typography.monoNumber}`}>{counter}</span>
        {action}
      </div>
    </section>
  )
}
