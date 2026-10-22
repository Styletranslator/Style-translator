import { getCover } from '../../constants/styleCovers'
import typography from '../../styles/typography.module.css'
import styles from './StyleCard.module.css'

// Figma `StyleCard` — State=Active(캐러셀 가운데)/Inactive, Size는 뷰포트로 CSS가 고름.
// 배치(className, position)는 캐러셀이 정하고 카드는 생김새만 책임.
export default function StyleCard({ ref, styleKey, label, number, isActive, className, position, onSelect }) {
  const cover = getCover(styleKey, label)

  return (
    <button
      ref={ref}
      type="button"
      role="radio"
      aria-checked={isActive}
      tabIndex={isActive ? 0 : -1}
      className={`${styles.card} ${className}`}
      data-state={isActive ? 'active' : 'inactive'}
      data-style={styleKey}
      data-position={position}
      onClick={onSelect}
    >
      <span className={styles.cover} aria-hidden="true">
        <span className={`${styles.number} ${typography.monoLabel}`}>STYLE {String(number).padStart(2, '0')}</span>
        <span className={`${styles.glyph} ${typography.coverGlyphMd}`}>{cover.glyph}</span>
      </span>
      <span className={`${styles.name} ${typography.cardNameSm}`}>{label}</span>
      <span className={`${styles.description} ${typography.cardSub}`}>{cover.description}</span>
    </button>
  )
}
