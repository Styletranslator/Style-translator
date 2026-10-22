// 도착 언어 — 백엔드에 언어 목록 API가 없어 프론트에 둡니다. code는 요청 바디의 target_lang.
export const LANGUAGES = [
  { code: 'en', label: '영어', short: 'EN' },
  { code: 'ko', label: '한국어', short: 'KO' },
  { code: 'ja', label: '일본어', short: 'JA' },
  { code: 'zh', label: '중국어', short: 'ZH' },
]

export const DEFAULT_LANGUAGE = 'en'
