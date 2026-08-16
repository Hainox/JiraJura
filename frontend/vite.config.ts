import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'node:path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // Регистрируем сам, явно (см. src/main.tsx) — с периодической проверкой
      // обновлений, а не только авто-инъекция плагина по умолчанию
      injectRegister: false,
      includeAssets: ['favicon.svg', 'icons.svg'],
      manifest: {
        name: 'Журнал обхода площадок САО',
        short_name: 'Обход САО',
        description: 'Электронный журнал обхода детских и спортивных площадок САО г. Москвы',
        theme_color: '#1e40af',
        background_color: '#f8fafc',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        // Без этого SPA-фолбэк (навигация → закэшированный index.html)
        // перехватывает ЛЮБУЮ навигацию, включая переход по /api/v1/... в
        // адресной строке — вместо реального запроса к бэкенду отдаётся
        // закэшированная страница логина
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
        runtimeCaching: [
          // API-ответы зависят от Authorization и района пользователя.
          // Их нельзя кэшировать по одному URL: Workbox не включает заголовок
          // Authorization в ключ runtime-кэша, поэтому ответ одного сотрудника
          // мог попасть другому (в том числе пустой ответ при таймауте сети).
          {
            urlPattern: /^\/api\/v1\/.*/,
            handler: 'NetworkOnly',
          },
          {
            urlPattern: /^https:\/\/.*\.tile\.openstreetmap\.org\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'tile-cache',
              expiration: { maxEntries: 5000, maxAgeSeconds: 60 * 60 * 24 * 30 }
            }
          }
        ]
      }
    })
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => '/api/v1' + path,
      },
    }
  }
})
