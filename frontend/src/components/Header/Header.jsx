import logoIcon from '../../assets/icon-logo.svg'
import styles from './Header.module.css'

export default function Header() {
  return (
    <header className={styles.header}>
      <h1 className={styles.logo}>
        <img src={logoIcon} width="24" height="24" alt="" />
        Style Translator
      </h1>
      <span className={styles.badge}>BETA</span>
    </header>
  )
}
