import { useEffect } from 'react'
import { prefetchRoute } from '@/lib/routePreload'

/** Глобальный слушатель префетча ленивых чанков по hover/focus.
 *
 * Любой элемент с атрибутом data-prefetch="/путь" запускает фоновую загрузку
 * чанка маршрута, когда на него наводят курсор (pointerover) или он получает
 * фокус с клавиатуры (focusin). Сам ничего не рендерит.
 */
export default function RoutePrefetcher() {
  useEffect(() => {
    const prefetchFromEvent = (e: Event) => {
      const target = e.target
      if (!(target instanceof Element)) return
      const path = target.closest('[data-prefetch]')?.getAttribute('data-prefetch')
      if (path) prefetchRoute(path)
    }
    // pointerover ловится и до клика на тач-устройствах (перед pointerdown),
    // поэтому префетч работает и на мобильных без отдельного touchstart.
    document.addEventListener('pointerover', prefetchFromEvent)
    document.addEventListener('focusin', prefetchFromEvent)
    return () => {
      document.removeEventListener('pointerover', prefetchFromEvent)
      document.removeEventListener('focusin', prefetchFromEvent)
    }
  }, [])
  return null
}
