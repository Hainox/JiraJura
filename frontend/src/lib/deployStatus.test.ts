import { describe, expect, it } from 'vitest'
import type { DeployEventOut } from '@/types'
import { DEPLOY_STUCK_AFTER_MS, deployRequestState } from './deployStatus'

const at = '2026-10-01T00:00:00Z'
const t0 = new Date(at).getTime()

function event(action: string, entityId: string | null, createdAt = at): DeployEventOut {
  return { id: `${action}-${entityId}`, action, entity_id: entityId, user_name: null, details: null, created_at: createdAt }
}

describe('deployRequestState', () => {
  it('запрос с результатом — выполнен, сколько бы времени ни прошло', () => {
    const request = event('deploy_requested', 'a')
    const events = [event('deploy_completed', 'a'), request]
    expect(deployRequestState(request, events, t0 + 10 * DEPLOY_STUCK_AFTER_MS)).toBe('done')
  })

  it('без результата — ждёт, а после порога — завис', () => {
    const request = event('deploy_requested', 'a')
    const events = [event('deploy_completed', 'b'), request]
    expect(deployRequestState(request, events, t0 + 60_000)).toBe('pending')
    expect(deployRequestState(request, events, t0 + DEPLOY_STUCK_AFTER_MS + 1)).toBe('stuck')
  })

  it('результат без entity_id не закрывает запрос без entity_id', () => {
    const request = event('deploy_requested', null)
    expect(deployRequestState(request, [event('deploy_completed', null), request], t0)).toBe('pending')
  })
})
