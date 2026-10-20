import styles from './StyleChip.module.css'

// Figma Pill Type=Chip — 현재 고른 스타일을 입력 패널에서도 보여줌. 모바일은 캐러셀이 대신함.
export default function StyleChip({ label }) {
  return (
    <span className={styles.chip}>
      <span className={styles.dot} aria-hidden="true" />
      {label}
    </span>
  )
}
