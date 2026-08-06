import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { registerSW } from 'virtual:pwa-register'
import { ThemeProvider } from '@/lib/theme'
import App from './App'
import './index.css'

// registerType: 'autoUpdate' активирует новую версию SW и перезагружает
// страницу сама, без вопроса пользователю — но только если вообще узнает
// об обновлении. Без явной регистрации это проверяется только при
// навигации, а вкладка, открытая долго (обход в поле), может застрять на
// старой закэшированной версии сколь угодно долго. registration.update()
// раз в час не даёт этому случиться.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (registration) {
      setInterval(() => registration.update(), 60 * 60 * 1000)
    }
  },
  onRegisterError(error) {
    console.error('SW registration error', error)
  },
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <App />
        </ThemeProvider>
        <Toaster
          position="top-center"
          toastOptions={{
            duration: 3000,
            style: {
              borderRadius: '10px',
              background: '#333',
              color: '#fff',
              fontSize: '14px',
              maxWidth: '360px',
            },
            success: {
              iconTheme: { primary: '#16a34a', secondary: '#fff' },
            },
            error: {
              iconTheme: { primary: '#dc2626', secondary: '#fff' },
            },
          }}
          gutter={8}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
)
