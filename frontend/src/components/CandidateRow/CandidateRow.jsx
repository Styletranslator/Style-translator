import eqIcon from '../../assets/eq-bars.svg'
import typography from '../../styles/typography.module.css'
import styles from './CandidateRow.module.css'

// Figma `CandidateRow` — Selected=true면 강조 배경 + 번호 amber + EqIcon
export default function CandidateRow({ number, text, isSelected, onSelect }) {
  return (
    <button type="button" className={styles.row} aria-pressed={isSelected} onClick={onSelect}>
      <span className={`${styles.number} ${typography.monoNumber}`}>{String(number).padStart(2, '0')}</span>
      <span className={`${styles.text} ${typography.bodyResult}`}>{text}</span>
      {isSelected && <img src={eqIcon} width="20" height="20" alt="" aria-hidden="true" />}
    </button>
  )
}
