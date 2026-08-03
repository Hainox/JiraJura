import type { Role } from '@/types'

export const ROLES: Role[] = ['inspector', 'reviewer', 'admin']

export const ROLE_LABELS: Record<Role, string> = {
  inspector: 'Инспектор',
  reviewer: 'Проверяющий',
  admin: 'Админ',
}
