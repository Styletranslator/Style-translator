import styles from './ResultPanel.module.css'

// 스켈레톤 줄 폭 — Figma `77:335` 비율. 빈 문자열은 문단 사이 간격.
const SKELETON_WIDTHS = ['86%', '91%', '82%', '56%', '', '89%', '84%', '67%']

// 진행률은 표시하지 않음 — /translate/long은 결과를 한 번에 돌려줘서 프론트가 진행 상황을 모름
export default function LongLoading({ styleLabel }) {
  return (
    <>
      <div className={styles.header}>
        <span>결과 · {styleLabel} · 장문</span>
        <span>번역 중…</span>
      </div>
      <div className={styles.longBody}>
        <div className={styles.skeleton} aria-hidden="true">
          {SKELETON_WIDTHS.map((width, index) =>
            width ? <span key={index} style={{ width }} /> : <i key={index} />,
          )}
        </div>
        <p className={styles.loadingNote}>긴 글은 문단을 나눠 번역한 뒤 이어 붙여서, 짧은 글보다 오래 걸려요.</p>
      </div>
    </>
  )
}
