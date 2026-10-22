import CandidateRow from '../CandidateRow/CandidateRow'
import LongLoading from './LongLoading'
import LongResult from './LongResult'
import typography from '../../styles/typography.module.css'
import styles from './ResultPanel.module.css'

// info: 헤더에 쓸 요청 당시 값 { styleLabel, languageLabel, sourceLength } — 로딩 중엔 진행 중인 요청 기준.
function PanelBody({ candidates, selected, onSelect, error, isLoadingLong, info }) {
  if (error) {
    return <p className={`${styles.error} ${typography.uiPill}`} role="alert">{error}</p>
  }
  if (isLoadingLong) {
    return <LongLoading styleLabel={info.styleLabel} />
  }
  // 장문 응답은 후보 1개 (client.js가 {candidates: [translation]}으로 맞춤)
  if (candidates.length === 1) {
    return <LongResult text={candidates[0]} info={info} />
  }
  return (
    <>
      <div className={`${styles.header} ${typography.monoLabel}`}>
        <span>
          결과 · {info.styleLabel} · <span className={styles.desktopOnly}>마음에 드는 번역을 고르세요</span>
          <span className={styles.mobileOnly}>하나를 고르세요</span>
        </span>
        <span className={styles.desktopOnly}>{candidates.length} TAKES</span>
      </div>
      {/* 후보는 서버가 준 순서 그대로이고 재정렬·삭제가 없어 index key로 충분 */}
      {candidates.map((candidate, index) => (
        <CandidateRow
          key={index}
          number={index + 1}
          text={candidate}
          isSelected={selected === index}
          onSelect={() => onSelect(index)}
        />
      ))}
    </>
  )
}

// aria-live 영역은 내용이 바뀌기 전부터 DOM에 있어야 스크린리더가 알림 → section은 항상 렌더.
export default function ResultPanel({ candidates, selected, onSelect, error, isTranslating, isLoadingLong, info }) {
  const hasContent = error || isLoadingLong || candidates.length > 0
  return (
    <section aria-live="polite" aria-label="번역 결과">
      {hasContent && (
        // 짧은 글 요청 중엔 이전 결과를 지우지 않고 흐리게 둠
        <div className={styles.panel} data-dimmed={isTranslating && !isLoadingLong}>
          <PanelBody
            candidates={candidates}
            selected={selected}
            onSelect={onSelect}
            error={error}
            isLoadingLong={isLoadingLong}
            info={info}
          />
        </div>
      )}
    </section>
  )
}
