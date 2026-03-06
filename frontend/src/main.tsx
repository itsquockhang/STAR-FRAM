import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CssBaseline } from '@mui/material'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { NerStoreProvider } from './state/nerStore'

const theme = createTheme({
  palette: {
    mode: 'light',
    background: {
      default: '#f6f7fb',
      paper: '#ffffff',
    },
  },
  shape: {
    borderRadius: 12,
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <NerStoreProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </NerStoreProvider>
    </ThemeProvider>
  </StrictMode>,
)
