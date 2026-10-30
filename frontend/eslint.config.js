import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

// 레이어 경계 — 규칙의 이유는 .claude/skills/frontend-clean-code/SKILL.md 「레이어」 참고.
// 의존 방향: components → (props만) / hooks → api / api → (외부 없음)
const NO_API = {
  group: ['**/api', '**/api/**'],
  message: 'components는 api를 직접 부르지 않습니다. hooks/의 훅을 거쳐 App(또는 컨테이너)에서 props로 내려주세요.',
}
const NO_DATA_HOOKS = {
  group: ['**/hooks', '**/hooks/**'],
  message: 'components는 프레젠테이션 전용입니다. 데이터 훅은 App(또는 컨테이너)에서 호출해 props로 내려주세요. UI 전용 훅은 컴포넌트 폴더 안에 두세요.',
}
const NO_COMPONENTS = {
  group: ['**/components', '**/components/**'],
  message: '하위 레이어(hooks/api/utils/constants)는 UI 컴포넌트에 의존하지 않습니다.',
}
const NO_REACT_IN_API = {
  name: 'react',
  message: 'api/는 순수 fetch 레이어입니다. React 상태는 hooks/에서 다룹니다.',
}

export default defineConfig([
  globalIgnores(['dist', 'coverage']),

  // ── 공통 ────────────────────────────────────────────────
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // 버그로 이어지는 것만 error
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^_', ignoreRestSiblings: true }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],

      // 나머지는 신호(warn) — CI를 막지 않음
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-nested-ternary': 'warn',
      'max-lines': ['warn', { max: 300, skipBlankLines: true, skipComments: true }],
      complexity: ['warn', 15],
    },
  },

  // ── 레이어 경계 ─────────────────────────────────────────
  {
    files: ['src/components/**/*.{js,jsx}'],
    rules: {
      'no-restricted-imports': ['error', { patterns: [NO_API, NO_DATA_HOOKS] }],
    },
  },
  {
    files: ['src/hooks/**/*.{js,jsx}', 'src/utils/**/*.js', 'src/constants/**/*.js'],
    rules: {
      'no-restricted-imports': ['error', { patterns: [NO_COMPONENTS] }],
    },
  },
  {
    files: ['src/api/**/*.js'],
    ignores: ['src/api/**/*.test.js'],
    rules: {
      'no-restricted-imports': [
        'error',
        { paths: [NO_REACT_IN_API], patterns: [NO_COMPONENTS, { group: ['**/hooks', '**/hooks/**'], message: 'api/는 hooks에 의존하지 않습니다 (역방향 의존).' }] },
      ],
    },
  },

  // ── 테스트 · 설정 파일은 완화 ───────────────────────────
  {
    files: ['**/*.test.{js,jsx}', '*.config.js'],
    languageOptions: { globals: { ...globals.node } },
    rules: {
      'max-lines': 'off',
    },
  },
])