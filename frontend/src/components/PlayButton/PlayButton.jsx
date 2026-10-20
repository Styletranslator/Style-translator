import playIcon from '../../assets/icon-play.svg'
import loadingIcon from '../../assets/icon-loading.svg'
import styles from './PlayButton.module.css'

export default function PlayButton({ isLoading, onClick }) {
  return (
    <button
      type="button"
      className={styles.button}
      aria-label="번역하기"
      aria-busy={isLoading}
      disabled={isLoading}
      onClick={onClick}
    >
      <img
        className={isLoading ? styles.loadingIcon : undefined}
        src={isLoading ? loadingIcon : playIcon}
        width="22"
        height="22"
        alt=""
      />
    </button>
  )
}
