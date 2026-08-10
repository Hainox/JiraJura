import { create } from 'zustand'
import { notify as toast } from '@/lib/toast'

// Временный "экскурсионный" режим для живого показа руководству: реальные
// данные видны как есть (карта/обходы/отчёты — обычная навигация), но
// действия, которые необратимо меняют реальные записи (принять обход,
// сменить статус замечания и т.п.), перехватываются на уровне обработчика
// ДО сетевого запроса — показываем тост вместо реального изменения. Так
// безопаснее, чем подделывать ответ API: некоторые onSuccess-колбэки
// читают поля из ответа (например, res.new_password при сбросе пароля) и
// упали бы на null посреди показа.
interface DemoModeState {
  enabled: boolean
  toggle: () => void
}

const STORAGE_KEY = 'demo_mode'

export const useDemoModeStore = create<DemoModeState>((set, get) => ({
  enabled: localStorage.getItem(STORAGE_KEY) === '1',
  toggle: () => {
    const next = !get().enabled
    localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
    set({ enabled: next })
  },
}))

/** Оборачивает обработчик реального изменения: в демо-режиме — тост вместо
 * запроса, иначе выполняет action как обычно. Использовать в местах, где
 * клик необратимо меняет реальные записи (принять обход, сменить статус,
 * удалить, сбросить пароль и т.п.). */
export function guardDemoAction(action: () => void) {
  if (useDemoModeStore.getState().enabled) {
    toast.success('🎬 Демо-режим: изменение показано, но не сохранено')
    return
  }
  action()
}

