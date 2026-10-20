import typography from '../../styles/typography.module.css'
import styles from './Badge.module.css'

// Figma `Badge` — 헤더 BETA, 입력 패널의 `장문 모드`(tone="accent")
export default function Badge({ children, tone = 'default', className }) {
  return (
    <span className={`${styles.badge} ${typography.monoLabel} ${className ?? ''}`} data-tone={tone}>
      {children}
    </span>
  )
}
