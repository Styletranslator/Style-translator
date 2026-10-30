import logoIcon from '../../assets/icon-logo.svg'
import Badge from '../Badge/Badge'
import typography from '../../styles/typography.module.css'
import styles from './Header.module.css'

export default function Header() {
  return (
    <header className={styles.header}>
      <h1 className={`${styles.logo} ${typography.logo}`}>
        <img src={logoIcon} width="24" height="24" alt="" />
        Style Translator
      </h1>
      <Badge>BETA</Badge>
    </header>
  )
}
