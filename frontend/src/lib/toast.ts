import toast from 'react-hot-toast'

// Дедуплицированные тосты: одинаковые сообщения в течение 2 секунд не дублируются
const recentToasts = new Map<string, number>()

function dedupe(msg: string): boolean {
  const now = Date.now()
  const last = recentToasts.get(msg)
  if (last && now - last < 2000) return false
  recentToasts.set(msg, now)
  // очищаем старые
  if (recentToasts.size > 20) {
    for (const [k, v] of recentToasts) {
      if (now - v > 5000) recentToasts.delete(k)
    }
  }
  return true
}

export const notify = {
  success: (msg: string) => {
    if (dedupe(msg)) toast.success(msg, { duration: 3000 })
  },
  error: (msg: string) => {
    if (dedupe(msg)) toast.error(msg, { duration: 4000 })
  },
  loading: (msg: string) => toast.loading(msg),
  dismiss: (id?: string) => toast.dismiss(id),
  promise: toast.promise,
}
