import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// tokens.css가 @layer 순서를 선언하므로 가장 먼저 불러옴. 나머지 우선순위는 레이어가 정함.
import './styles/tokens.css'
import './styles/typography.module.css'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
