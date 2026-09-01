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
//
// Только тост с кнопкой, никакого тихого auto-apply по document.hidden —
// он был в первой версии этого PR и Codex справедливо указал на реальную
// дыру: SW-регистрация одна на весь origin, а не на вкладку. skipWaiting()
// из ЛЮБОЙ вкладки (в т.ч. свёрнутой в фоне) активирует новый воркер сразу
// для ВСЕХ вкладок сразу, и КАЖДАЯ из них (см. vite-plugin-pwa client:
// wb.addEventListener('controlling', ...)) тут же сама себя перезагружает —
// включая ту, что открыта и активна прямо сейчас, с незасохранённым фото
// обхода. Проверка document.visibilityState в фоновой вкладке ничего не
// знает про то, что другая вкладка того же origin в этот момент видима.
// Поэтому обновление применяется только по явному клику пользователя.

// let с безопасным no-op по умолчанию, не const = registerSW(...) — на
// момент вызова registerSW() ниже applyUpdate уже объявлена (используется
// только изнутри onNeedRefresh, синхронно раньше сработать не может, см.
// node_modules/vite-plugin-pwa/dist/client/build/register.js: единственный
// путь к onNeedRefresh лежит за `await import('workbox-window')`, то есть
// строго после того, как сам registerSW() уже вернул управление и переменная
// ниже успела бы получить настоящее значение), но держать здесь голый `let`
// без инициализатора и полагаться на этот порядок — subtle: любой будущий
// рефакторинг библиотеки ломает это без предупреждения на этапе сборки.
let updateSW: (reloadPage?: boolean) => Promise<void> = async () => {}

function applyUpdate() {
  updateSW(true)
}

updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    toast(
      (t) => (
        <div className="flex items-center gap-3">
          <span>Доступна новая версия приложения</span>
          <button
            type="button"
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
