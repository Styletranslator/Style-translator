import { useRef } from 'react'
import StyleCard from '../StyleCard/StyleCard'
import typography from '../../styles/typography.module.css'
import styles from './StyleCarousel.module.css'

const SWIPE_THRESHOLD = 40

// 선택된 카드를 가운데에 두고 바로 앞·뒤 카드만 보여줌. 나머지는 hidden으로 숨김.
function getPosition(index, activeIndex, count) {
  if (index === activeIndex) return 'active'
  if (count > 2 && index === (activeIndex - 1 + count) % count) return 'prev'
  if (index === (activeIndex + 1) % count) return 'next'
  return 'hidden'
}

export default function StyleCarousel({ styles: styleMap, value, onChange }) {
  const entries = Object.entries(styleMap)
  const activeIndex = Math.max(0, entries.findIndex(([key]) => key === value))
  const cardRefs = useRef({})
  const swipe = useRef({ startX: null, swiped: false })

  function selectBy(offset, { focus = false } = {}) {
    const [key] = entries[(activeIndex + offset + entries.length) % entries.length]
    onChange(key)
    if (focus) cardRefs.current[key]?.focus()
  }

  function handleKeyDown(e) {
    if (e.key === 'ArrowLeft') selectBy(-1, { focus: true })
    else if (e.key === 'ArrowRight') selectBy(1, { focus: true })
    else return
    e.preventDefault()
  }

  function handlePointerDown(e) {
    swipe.current = { startX: e.clientX, swiped: false }
  }

  function handlePointerUp(e) {
    const { startX } = swipe.current
    if (startX === null) return
    const dx = e.clientX - startX
    swipe.current.startX = null
    if (Math.abs(dx) < SWIPE_THRESHOLD) return
    swipe.current.swiped = true
    selectBy(dx < 0 ? 1 : -1)
  }

  function handleCardClick(key) {
    // 스와이프 끝에 따라오는 click은 무시 — 안 그러면 손가락이 놓인 카드가 한 번 더 선택됨.
    if (swipe.current.swiped) {
      swipe.current.swiped = false
      return
    }
    onChange(key)
  }

  return (
    <section className={styles.carousel}>
      <p className={`${styles.eyebrow} ${typography.monoEyebrow}`} aria-hidden="true">NOW CHOOSING · 말투 고르기</p>
      <div
        className={styles.cards}
        role="radiogroup"
        aria-label="말투 선택"
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
      >
        {entries.map(([key, label], index) => (
          <StyleCard
            key={key}
            ref={(node) => { cardRefs.current[key] = node }}
            styleKey={key}
            label={label}
            number={index + 1}
            isActive={index === activeIndex}
            className={styles.slot}
            position={getPosition(index, activeIndex, entries.length)}
            onSelect={() => handleCardClick(key)}
          />
        ))}
      </div>
    </section>
  )
}
