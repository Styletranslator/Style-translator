# Frontend — CLAUDE.md

React 19 + Vite. 상태관리 라이브러리 없음 (`useState` + 커스텀 훅).

## Commands

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run lint
npm run build
npm test         # vitest run
```

`npm install`은 **반드시 `frontend/`에서** 실행하세요. 루트에서 하면 루트 `node_modules`가 생깁니다.

## Structure

| 파일 | 역할 |
|---|---|
| `src/App.jsx` | 화면 전체. 마운트 시 `fetchStyles()`로 드롭다운 채움 (실패 시 `FALLBACK_STYLES`) |
| `src/api/client.js` | `fetchStyles()`, `fetchTranslation()` — fetch 래퍼 |
| `src/hooks/useTranslate.js` | `{candidates, selected, setSelected, loading, error, translate}` — 번역 호출 + 후보 3개/선택 상태 관리 |
| `src/App.css`, `src/index.css` | 스타일 |

## API 연동

베이스 URL은 `src/api/client.js`에서:

```js
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
```

배포 시 `.env`에 `VITE_API_BASE`를 지정하면 됩니다 (코드 수정 불필요).
백엔드 CORS는 `backend/core/config.py`의 `ALLOWED_ORIGINS`에 `http://localhost:5173`만 등록돼 있습니다.

요청 바디는 snake_case로 변환해서 보냅니다 — `{text, target_lang, style}`.
`fetchTranslation()`은 `text.length > SHORT_LIMIT`(1,000, 백엔드와 동일)면 `/translate/long`으로 보내고,
장문 응답 `{translation}`을 `{candidates: [translation]}`으로 맞춰 반환합니다.

**응답 envelope:** 백엔드는 모든 응답을 `{success, data}` / `{success, error: {code, message}}`로
감싸 보냅니다. `client.js`의 `unwrap()`이 껍데기를 벗겨내므로 **이 파일 밖에서는 응답 형식을
몰라도 됩니다** — 컴포넌트와 훅은 `data` 알맹이만 받습니다.

**에러 처리:** `unwrap()`이 `error.message`를 `Error`로 던지고 (`error.code`도 함께 붙임),
`useTranslate`가 그것을 `error` 상태에 담아 `App.jsx`가 표시합니다.
→ 백엔드 응답 형식이 바뀌면 `client.js`의 `unwrap()` 한 함수만 수정하면 됩니다.

## Testing

vitest, 기본 environment는 `node`입니다.
`src/api/client.test.js`는 `vi.stubGlobal('fetch', ...)`로 fetch를 스텁하므로 jsdom이 필요 없습니다.

컴포넌트 렌더 테스트를 추가하려면 `@testing-library/react` + `jsdom` 설치와
`vite.config.js`에 `test: { environment: 'jsdom' }` 설정이 필요합니다 (현재 미설치).
