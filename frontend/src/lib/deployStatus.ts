import type { DeployEventOut } from '@/types'

/** Сколько ждать, пока deploy-watcher (cron раз в минуту) возьмёт запрос и
 * запишет результат. Деплой идёт 1–3 минуты; дольше — значит, watcher не
 * работает: так было с августа по 30.09.2026, и история месяц показывала
 * одни крутящиеся «Запрошен деплой», не давая понять, что что-то не так. */
export const DEPLOY_STUCK_AFTER_MS = 10 * 60 * 1000

export type DeployRequestState = 'done' | 'pending' | 'stuck'

/** Результат пишется отдельным событием deploy_completed с тем же entity_id. */
export function deployRequestState(
  request: DeployEventOut,
  events: DeployEventOut[],
  now: number = Date.now(),
): DeployRequestState {
  const done = events.some(
    (e) => e.action === 'deploy_completed' && e.entity_id !== null && e.entity_id === request.entity_id,
  )
  if (done) return 'done'
  return now - new Date(request.created_at).getTime() > DEPLOY_STUCK_AFTER_MS ? 'stuck' : 'pending'
}
