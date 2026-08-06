import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './index.css'

// registerType: 'autoUpdate' активирует новую версию SW в фоне сама
// (skipWaiting+clientsClaim), но уже открытая вкладка продолжает работать
// на СТАРОМ загруженном JS, пока не перезагрузится — controllerchange
// сигнализирует именно момент, когда новый SW реально взял управление.
// Без этого слушателя вкладка, открытая часами в поле, может никогда не
// увидеть свежий код сама по себе (это и было причиной того, что часть
// пользователей словила уже исправленный сегодня баг с вылетом на логин
// при разворачивании PWA из фона — старый JS с багом просто не сменился
// на новый). Перезагружаем только когда вкладка не на экране — на
// следующий возврат в приложение человек увидит уже свежую версию, а не
// потеряет то, что заполнял, из-за перезагрузки посреди работы.
if ('serviceWorker' in navigator) {
  let reloaded = false
  const reloadIfHidden = () => {
    if (reloaded || document.visibilityState !== 'hidden') return
    reloaded = true
    window.location.reload()
  }
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    reloadIfHidden()
    document.addEventListener('visibilitychange', reloadIfHidden)
  })
}

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
        <App />
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
