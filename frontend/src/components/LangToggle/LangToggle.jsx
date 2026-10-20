import { useRef } from 'react'
import styles from './LangToggle.module.css'

// 라디오 그룹 동작: ←→로 이동하면 바로 선택되고, 탭 정지는 선택된 칸 하나뿐.
export default function LangToggle({ languages, value, onChange }) {
  const segmentRefs = useRef([])
  const activeIndex = languages.findIndex((language) => language.code === value)

  function handleKeyDown(e) {
    const offset = { ArrowLeft: -1, ArrowRight: 1 }[e.key]
    if (!offset) return
    e.preventDefault()
    const nextIndex = (activeIndex + offset + languages.length) % languages.length
    onChange(languages[nextIndex].code)
    segmentRefs.current[nextIndex]?.focus()
  }

  return (
    <div className={styles.toggle} role="radiogroup" aria-label="도착 언어" onKeyDown={handleKeyDown}>
      {languages.map((language, index) => (
        <button
          key={language.code}
          ref={(node) => { segmentRefs.current[index] = node }}
          type="button"
          role="radio"
          aria-checked={language.code === value}
          aria-label={language.label}
          tabIndex={language.code === value ? 0 : -1}
          className={styles.segment}
          onClick={() => onChange(language.code)}
        >
          <span className={styles.full}>{language.label}</span>
          <span className={styles.short}>{language.short}</span>
        </button>
      ))}
    </div>
  )
}
