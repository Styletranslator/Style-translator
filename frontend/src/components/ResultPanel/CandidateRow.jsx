import eqIcon from '../../assets/eq-bars.svg'
import styles from './ResultPanel.module.css'

export default function CandidateRow({ number, text, isSelected, onSelect }) {
  return (
    <button type="button" className={styles.row} aria-pressed={isSelected} onClick={onSelect}>
      <span className={styles.rowNumber}>{String(number).padStart(2, '0')}</span>
      <span className={styles.rowText}>{text}</span>
      {isSelected && <img src={eqIcon} width="20" height="20" alt="" aria-hidden="true" />}
    </button>
  )
}
