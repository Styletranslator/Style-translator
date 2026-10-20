import { getCover } from '../../constants/styleCovers'
import styles from './StyleCarousel.module.css'

export default function StyleCard({ ref, styleKey, label, number, position, onSelect }) {
  const cover = getCover(styleKey, label)
  const isActive = position === 'active'

  return (
    <button
      ref={ref}
      type="button"
      role="radio"
      aria-checked={isActive}
      tabIndex={isActive ? 0 : -1}
      className={styles.card}
      data-position={position}
      data-style={styleKey}
      onClick={onSelect}
    >
      <span className={styles.cover} aria-hidden="true">
        <span className={styles.number}>STYLE {String(number).padStart(2, '0')}</span>
        <span className={styles.glyph}>{cover.glyph}</span>
      </span>
      <span className={styles.name}>{label}</span>
      <span className={styles.description}>{cover.description}</span>
    </button>
  )
}
