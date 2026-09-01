import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import toast, { Toaster } from 'react-hot-toast'
import { RefreshCw } from 'lucide-react'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './index.css'

const UPDATE_TOAST_ID = 'sw-update'

// registerType: 'prompt' (см. vite.config.ts) — плагин находит новый SW, но
// не активирует его сам, а вызывает этот колбэк и ждёт applyUpdate().
// Если вкладка сейчас не на экране — обновляемся сразу, без вопросов
// (перезагрузка ничего не потеряет, никто не смотрит). Если человек активно
// работает в приложении — молча заменять код под ним рискованно (пример,
// который уже стоил времени: вылет на логин при развороте PWA из фона на
// старом JS), поэтому вместо этого показываем тост с кнопкой «Обновить» и
// откладываем обновление до клика или до момента, когда вкладка всё же
// свернётся — тогда применяем и без клика.
function applyUpdate() {
  updateSW(true)
}

const updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    if (document.visibilityState === 'hidden') {
      applyUpdate()
      return
    }
    toast(
      (t) => (
        <div className="flex items-center gap-3">
          <span>Доступна новая версия приложения</span>
          <button
            onClick={() => {
              toast.dismiss(t.id)
              applyUpdate()
            }}
            className="btn-primary text-xs py-1.5 px-3 shrink-0 flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" />
            Обновить
          </button>
        </div>
      ),
      { id: UPDATE_TOAST_ID, duration: Infinity }
    )
    const applyWhenHidden = () => {
      if (document.visibilityState !== 'hidden') return
      document.removeEventListener('visibilitychange', applyWhenHidden)
      toast.dismiss(UPDATE_TOAST_ID)
      applyUpdate()
    }
    document.addEventListener('visibilitychange', applyWhenHidden)
  },
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
