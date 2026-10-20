---
name: frontend-clean-code
description: 말투 번역기 frontend/ 코드를 작성·수정·리팩터링할 때 사용. 컴포넌트/훅/API 레이어 구조, 상태관리 선택 기준, 스타일링, 네이밍, 테스트 규칙과 작업 완료 체크리스트를 제공한다.
---

# Frontend Clean Code — 말투 번역기

이 문서의 규칙은 전부 **"6개월 뒤 처음 보는 팀원이 한 파일만 열어도 이해하고 고칠 수 있는가"**라는
기준에서 나왔다. 규칙이 상황과 안 맞으면 규칙을 어기지 말고, 이유를 PR에 적고 이 문서를 고친다.

기계적으로 판정되는 규칙은 `frontend/eslint.config.js`가 강제한다. 이 문서는 린트가 못 잡는
**판단**을 다룬다. 화면의 생김새는 `frontend/DESIGN.md`가 기준이다.

---

## 1. 레이어 — 의존은 한 방향으로만

```
src/
├── main.jsx            진입점. Provider 조립만.
├── App.jsx             컨테이너. 데이터 훅을 호출하고 컴포넌트에 props로 연결.
├── api/                fetch + envelope 해제. React를 모름.
├── hooks/              데이터·도메인 로직 훅 (TanStack Query, 파생 상태).
├── components/         프레젠테이션. props in → JSX out.
│   └── StyleCarousel/
│       ├── StyleCarousel.jsx
│       ├── StyleCarousel.module.css
│       └── useCarouselKeys.js   ← 이 컴포넌트만 쓰는 UI 훅은 여기
├── constants/          스타일 커버 매핑, 언어 목록 등 정적 데이터.
└── utils/              순수 함수 (입력 → 출력, 부수효과 없음).
```

**의존 방향:** `App → hooks → api`, `App → components`. 역방향은 린트 에러.

| 레이어 | 할 수 있는 것 | 하면 안 되는 것 |
|---|---|---|
| `api/` | fetch, 요청 바디 변환(camel→snake), envelope 해제, 응답 형태 정규화 | React import, 상태, UI 문구 결정 |
| `hooks/` | api 호출, 캐싱, 로딩/에러 상태, 파생 값 계산 | JSX 반환, 컴포넌트 import |
| `components/` | props 렌더, 사용자 이벤트를 콜백으로 올림, UI 전용 상태(열림/hover/포커스) | api/hooks import, 비즈니스 규칙 판단 |
| `App.jsx` | 훅 호출, 컴포넌트 배치, 콜백 연결 | 긴 로직(→ 훅으로), 마크업 세부(→ 컴포넌트로) |

**왜:** 백엔드 응답이 바뀌면 `api/`만, 디자인이 바뀌면 `components/`만 고치면 되도록 변경 이유별로
파일을 나눈다. 컴포넌트가 api를 직접 부르면 디자인 변경과 API 변경이 같은 파일에서 충돌한다.
컴포넌트가 props만 받으면 API 없이도 렌더 테스트·미리보기가 가능하다.

> 페이지가 2개 이상으로 늘면 `App.jsx` 대신 `pages/<Name>Page.jsx`가 컨테이너 역할을 한다.
> 그때도 의존 방향은 같다.

---

## 2. 상태 — 어디에 둘지 먼저 정한다

새 상태를 만들기 전에 위에서부터 차례로 묻는다. 처음 "예"가 나오는 곳에 둔다.

| 질문 | 예 → 둘 곳 |
|---|---|
| 다른 상태/props에서 계산할 수 있나? | **상태로 만들지 않는다.** 렌더 중 계산 (`const isLong = text.length > SHORT_LIMIT`) |
| 서버에서 온 데이터인가? (스타일 목록, 번역 결과) | **TanStack Query** — `useQuery` / `useMutation` |
| 한 컴포넌트 안에서만 쓰나? | 그 컴포넌트의 `useState` |
| 부모-자식 2단계 안에서 공유하나? | 공통 부모의 `useState` + props |
| 멀리 떨어진 여러 컴포넌트가 공유하나? (예: 히스토리, 즐겨찾기) | **Zustand** 스토어 (`src/stores/`) |
| 새로고침 후에도 유지돼야 하나? | Zustand `persist` 미들웨어 |

**왜:** 상태가 많을수록 동기화 버그가 는다. 계산 가능한 값을 상태로 두면 "원본은 바뀌었는데
복사본은 안 바뀐" 버그가 생긴다. 서버 데이터를 `useState`로 들면 로딩·에러·캐시·중복요청을
매번 손으로 짜야 한다 — TanStack Query는 그걸 표준화한다.

### TanStack Query 규칙
- 설치: `npm i @tanstack/react-query` (반드시 `frontend/`에서). `main.jsx`에서 `QueryClientProvider`로 감싼다.
- query key는 `hooks/queryKeys.js` 한 곳에서 관리: `export const queryKeys = { styles: ['styles'] }`
- `useQuery`/`useMutation`은 **`hooks/` 안에서만** 호출하고, 컴포넌트에는 필요한 값만 넘긴다.
  ```js
  // hooks/useStyles.js
  export function useStyles() {
    const { data = FALLBACK_STYLES, isError } = useQuery({
      queryKey: queryKeys.styles,
      queryFn: fetchStyles,
      staleTime: Infinity, // 스타일 목록은 세션 중 안 바뀜
    })
    return { styles: data, isFallback: isError }
  }
  ```
- 번역은 `useMutation`. 후보 선택 인덱스(`selected`)는 서버 상태가 아니므로 훅 안의 `useState`로 따로 둔다.
- 연타 방지: 버튼 `disabled={isPending}`. 결과 뒤섞임이 걱정되면 `mutation.reset()` 후 재요청.

### Zustand 규칙
- **필요해질 때만 설치한다.** 지금(단일 화면) 구조에선 불필요. 히스토리/즐겨찾기 기능이 들어올 때 도입.
- 스토어 하나에 하나의 관심사 (`useHistoryStore`, `useFavoritesStore`). 거대 단일 스토어 금지.
- 컴포넌트에선 셀렉터로 필요한 조각만 구독: `useHistoryStore((s) => s.items)` — 전체 구독은 불필요한 리렌더.
- 서버 데이터를 Zustand에 복사하지 않는다 (그건 Query 캐시의 일).

---

## 3. 컴포넌트

- **한 파일 = 한 컴포넌트**, 파일명 = 컴포넌트명 (PascalCase). 기본은 `export default`.
- **크기 신호:** JSX가 화면 한 번에 안 보이면(대략 80줄) 쪼갠다. 파일이 300줄을 넘으면 린트 `max-lines`가 경고한다.
  쪼갤 단위는 "이름 붙일 수 있는 화면 덩어리" — `ResultList` 안의 `ResultRow`처럼.
- **props**
  - 구조분해로 받는다: `function ResultRow({ index, text, isSelected, onSelect })`
  - 불리언은 `is/has/can` 접두사, 이벤트 콜백은 `on` 접두사 (`onSelect`, `onStyleChange`).
  - 부모 쪽 핸들러는 `handle` 접두사 (`handleStyleChange`) — 누가 정의하고 누가 받는지가 이름에 드러난다.
  - props가 7개를 넘으면 컴포넌트 책임이 너무 많다는 신호. 쪼개거나 `children`으로 조립한다.
  - 불필요한 객체 통째 전달 금지 — 쓰는 필드만 넘긴다 (변경 영향 범위가 줄어든다).
- **조건부 렌더**
  - 중첩 삼항 금지(린트 경고). 분기가 3개 이상이면 early return 또는 매핑 객체.
  - `{count && <X/>}` 금지 — `0`이 화면에 찍힌다. `{count > 0 && <X/>}`.
- **리스트 key:** 안정적인 id가 있으면 id. 서버 후보처럼 순서가 고정이고 재정렬/삭제가 없으면 index 허용 — 주석으로 이유를 남긴다.
- **접근성은 기본값:** 클릭 가능한 건 `<button>`(div onClick 금지), 아이콘 버튼엔 `aria-label`,
  선택 상태는 `aria-pressed`/`aria-checked`. 근거는 DESIGN.md의 각 컴포넌트 항목.
- **`useEffect`는 마지막 수단.** 외부 시스템(DOM API, 구독, 타이머)과 동기화할 때만 쓴다.
  props → state 복사, 이벤트에 대한 반응, 데이터 fetch에는 쓰지 않는다
  (각각 렌더 중 계산 / 이벤트 핸들러 / TanStack Query).

---

## 4. 훅

- 이름은 `use` + 무엇을 주는지 (`useStyles`, `useTranslation`, `useCarouselKeys`).
- **반환은 객체**로 — 호출부가 필요한 것만 꺼내고, 나중에 필드를 추가해도 호출부가 안 깨진다.
  (값 2개짜리 단순 토글 정도만 배열 허용)
- 반환 값 이름은 화면 언어로: `isTranslating`이 `mutation.isPending`보다 읽힌다. 라이브러리 객체를 통째로 반환하지 않는다 — 나중에 라이브러리를 바꿔도 컴포넌트가 안 바뀌게.
- 훅 하나가 서로 무관한 두 가지를 하면 나눈다.

---

## 5. API 레이어

- 현재 `api/client.js`의 `unwrap()` 패턴을 유지한다 — envelope을 아는 곳은 여기 한 군데.
- 응답 형태 정규화(장문 `{translation}` → `{candidates: [...]}`)도 여기서. 위 레이어는 한 가지 형태만 안다.
- 에러는 `Error`(+ `code`)로 던진다. 사용자에게 보여줄 문구 선택은 hooks/컴포넌트의 몫이고,
  내부 코드(`TRANSLATION_ENGINE_ERROR`)를 화면에 그대로 노출하지 않는다.
- 백엔드와 공유하는 상수(`SHORT_LIMIT`, `MAX_LENGTH`)는 출처 파일을 주석으로 남긴다 — 한쪽만 바뀌는 사고 방지.
- 파일이 커지면 리소스별로 나눈다: `api/http.js`(unwrap, base URL) + `api/styles.js` + `api/translate.js`.

---

## 6. 스타일링

- **디자인 토큰은 `src/index.css`의 `:root` 한 곳에만.** 컴포넌트 CSS는 `var(--…)`만 쓰고 hex 값을 직접 쓰지 않는다.
  (현재 `App.css`에도 `:root` 토큰이 있음 — 리디자인 시 index.css로 합치고 제거)
- **컴포넌트 스타일은 CSS Modules** (`Foo.module.css`, 컴포넌트 옆에 둠). Vite 기본 지원이라 설치 불필요.
  **왜:** 전역 클래스는 이름 충돌과 "이 클래스 지워도 되나?" 불안을 만든다. 모듈은 컴포넌트를 지우면 스타일도 같이 사라진다.
- 클래스명은 역할 기준 camelCase (`styles.coverText`), 생김새 기준 금지 (`styles.orangeBox` ✗).
- 상태 표현은 data 속성 또는 aria 속성으로: `[aria-pressed='true'] { … }` — 접근성과 스타일이 한 소스를 공유.
- 반응형 기준점은 DESIGN.md를 따른다 (모바일 ≤ 640px).

---

## 7. 네이밍 · 파일

| 대상 | 규칙 | 예 |
|---|---|---|
| 컴포넌트 파일/폴더 | PascalCase | `StyleCarousel/StyleCarousel.jsx` |
| 훅 | camelCase, `use` 접두사 | `useStyles.js` |
| 상수 | `UPPER_SNAKE` | `SHORT_LIMIT`, `STYLE_COVERS` |
| 유틸 | 동사로 시작 | `formatCount`, `toSnakeCase` |
| 테스트 | 대상 옆에 `.test.js(x)` | `useStyles.test.js` |

- 약어 금지 (`cand`, `idx`, `res` 대신 `candidate`, `index`, `response`) — 단, 콜백 인자 `e` 정도는 허용.
- 주석은 **왜**를 쓴다. 무엇을 하는지는 코드가 말해야 한다. 백엔드와 맞물린 값, 의도적인 예외(index key 등)는 반드시 주석.
- barrel 파일(`index.js` 재수출)은 만들지 않는다 — 파일 수가 적어 이득이 없고, import 경로가 실제 위치를 숨긴다.

---

## 8. 테스트

- **우선순위:** `utils/` 순수 함수 > `api/` (fetch 스텁) > `hooks/` > 컴포넌트.
  로직을 hooks/utils로 빼 두면 대부분 jsdom 없이 테스트된다 — 레이어 분리의 또 다른 이득.
- 컴포넌트 테스트가 필요해지면 `@testing-library/react` + `jsdom` 설치, 파일 상단 `// @vitest-environment jsdom`.
- 테스트 이름은 한국어 문장으로 동작을 쓴다: `it('1000자를 넘으면 장문 엔드포인트로 보낸다')`.
- 구현 세부(내부 state 값)가 아니라 관찰 가능한 결과(반환값, 렌더된 텍스트, 호출된 URL)를 검증한다.

---

## 9. 작업 절차

**시작 전**
1. `frontend/CLAUDE.md` 확인. 화면 작업이면 `frontend/DESIGN.md`도.
2. 바꿀 코드가 어느 레이어인지 정한다. 두 레이어 이상에 걸치면 레이어별로 나눠 작업한다.
3. 새 라이브러리가 필요하면 먼저 사용자에게 이유와 함께 확인한다 (TanStack Query는 사전 승인됨, Zustand는 2장 기준 충족 시).

**작성 중**
- 동작 변경과 리팩터링을 한 커밋에 섞지 않는다 — 리뷰어가 "무엇이 바뀌었나"를 구분할 수 없다.
- 기존 동작(장문 분기, envelope 해제, fallback 스타일)을 지운다면 의도인지 다시 확인한다.

**끝내기 전 — 모두 통과해야 완료**
```bash
cd frontend
npm run lint      # 에러 0. 경고는 이유가 있으면 남기되 응답에 언급
npm test
npm run build
```
4. 구조(파일 추가/이동, 훅 반환 형태)가 바뀌었으면 `frontend/CLAUDE.md`의 Structure 표를 갱신한다.
5. git commit/push는 사용자가 요청할 때만 한다.
