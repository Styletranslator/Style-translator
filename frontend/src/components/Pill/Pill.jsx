import typography from '../../styles/typography.module.css'
import styles from './Pill.module.css'

// Figma `Pill` — Type=Chip(현재 스타일 표시, 오렌지 dot) / Type=Select(버튼으로 쓸 때, 아이콘 숨김).
// onClick이 있으면 <button>, 없으면 표시용 <span>.
export default function Pill({ type = 'select', children, onClick, className, ...ariaProps }) {
  const classNames = `${styles.pill} ${typography.uiPill} ${className ?? ''}`
  const content = (
    <>
      {type === 'chip' && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </>
  )

  if (!onClick) {
    return <span className={classNames} data-type={type}>{content}</span>
  }
  return (
    <button type="button" className={classNames} data-type={type} onClick={onClick} {...ariaProps}>
      {content}
    </button>
  )
}
