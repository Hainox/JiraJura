import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sitesApi, inspectionsApi, checklistsApi, authApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { SiteOut, ChecklistTemplateOut, InspectionOut, UserAdminOut } from '@/types'
import { ArrowLeft, Play, Eye, Clock, UserCog } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе',
  completed: 'Завершён', issues_found: 'Есть нарушения', critical: 'Критический',
}
const STATUS_COLORS: Record<string, string> = {
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  issues_found: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
  planned: 'bg-gray-100 text-gray-600',
}

export default function SiteDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const siteId = id!
  const user = useAuthStore((s) => s.user)

  const { data: site, isLoading } = useQuery<SiteOut>({
    queryKey: ['site', siteId],
    queryFn: () => sitesApi.get(siteId),
    enabled: !!siteId,
  })

  const { data: checklists } = useQuery<ChecklistTemplateOut[]>({
    queryKey: ['checklist-template', site?.type],
    queryFn: () => checklistsApi.template({ site_type: site!.type }),
    enabled: !!site?.type,
  })

  // all_in_district — иначе инспектор видел бы в истории площадки только
  // свои обходы, и обход коллеги (важно знать, что площадку уже накрыли)
  // был бы попросту не виден.
  const { data: inspectionsData } = useQuery<{ items: InspectionOut[] }>({
    queryKey: ['inspections', siteId],
    queryFn: () => inspectionsApi.list({ site_id: siteId, all_in_district: user?.role === 'inspector' || undefined }),
    enabled: !!siteId,
  })

  const startMutation = useMutation({
    mutationFn: () => inspectionsApi.create(siteId),
    onSuccess: (inspection) => {
      toast.success('Обход начат!')
      navigate(`/inspections/${inspection.id}`)
    },
    onError: () => toast.error('Ошибка при создании обхода'),
  })

  const isReviewerOrAdmin = user?.role === 'reviewer' || user?.role === 'admin'
  const inspections = inspectionsData?.items ?? []

  // Назначение площадки инспектору — ориентир для распределения обходов
  // внутри района, не хард-ограничение (см. комментарий у
  // Site.assigned_inspector_id в backend/app/models.py): любой инспектор
  // района по-прежнему может начать обход любой площадки.
  const { data: usersData } = useQuery<UserAdminOut[]>({
    queryKey: ['users'],
    queryFn: authApi.listUsers,
    enabled: isReviewerOrAdmin,
  })
  const districtInspectors = (usersData ?? []).filter(
    (u) => u.role === 'inspector' && u.district_id === site?.district?.id
  )
  const [selectedInspectorId, setSelectedInspectorId] = useState('')
  useEffect(() => {
    setSelectedInspectorId(site?.assigned_inspector?.id ?? '')
  }, [site?.assigned_inspector?.id])

  const assignMutation = useMutation({
    mutationFn: (inspectorId: string | null) => sitesApi.assign(siteId, inspectorId),
    onSuccess: () => {
      toast.success('Назначение обновлено')
      queryClient.invalidateQueries({ queryKey: ['site', siteId] })
    },
    onError: () => toast.error('Не удалось обновить назначение'),
  })

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Загрузка...</div>
      </div>
    )
  }

  if (!site) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Площадка не найдена</div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/')} data-prefetch="/" className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-lg truncate">{site.courtyard?.name ?? 'Площадка'}</h1>
          <p className="text-blue-200 text-xs truncate">{site.district?.name ?? 'Район не указан'}</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* Инфо-карточка */}
        <div className="card">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-gray-400 text-xs">Тип</div>
              <div className="font-medium mt-0.5">{site.type}</div>
            </div>
            <div>
              <div className="text-gray-400 text-xs">Площадь</div>
              <div className="font-medium mt-0.5">{site.area_m2} м²</div>
            </div>
            <div className="col-span-2">
              <div className="text-gray-400 text-xs">Район</div>
              <div className="font-medium mt-0.5">{site.district?.name}</div>
            </div>
            {!isReviewerOrAdmin && (
              <div className="col-span-2">
                <div className="text-gray-400 text-xs">Назначена</div>
                <div className="font-medium mt-0.5">{site.assigned_inspector?.full_name ?? 'Не назначена'}</div>
              </div>
            )}
          </div>
        </div>

        {/* Назначение инспектора — только для проверяющего/админа */}
        {isReviewerOrAdmin && (
          <div className="card">
            <h2 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <UserCog className="w-4 h-4 text-gray-400" />
              Назначенный инспектор
            </h2>
            <div className="flex gap-2">
              <select
                className="input-field text-sm flex-1"
                value={selectedInspectorId}
                onChange={(e) => setSelectedInspectorId(e.target.value)}
              >
                <option value="">Не назначен</option>
                {districtInspectors.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
              <button
                onClick={() => assignMutation.mutate(selectedInspectorId || null)}
                disabled={assignMutation.isPending || selectedInspectorId === (site.assigned_inspector?.id ?? '')}
                className="btn-primary text-sm px-4 disabled:opacity-40"
              >
                Сохранить
              </button>
            </div>
            {districtInspectors.length === 0 && (
              <p className="text-xs text-gray-400 mt-2">В этом районе пока нет зарегистрированных инспекторов.</p>
            )}
          </div>
        )}

        {/* Чек-лист предпросмотр */}
        {checklists && checklists.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-gray-800 mb-3">Чек-лист обхода</h2>
            {checklists.map((tmpl) => (
              <div key={tmpl.id} className="mb-3 last:mb-0">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1.5">{tmpl.name}</div>
                <div className="space-y-1.5">
                  {tmpl.items.map((item) => (
                    <div key={item.id} className="text-sm text-gray-700 flex items-start gap-2">
                      <span className="text-gray-300 mt-0.5">•</span>
                      <span>{item.question}</span>
                      {item.is_critical && <span className="badge badge-nok shrink-0 text-[10px]">важно</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* История обходов (всегда показываем, если есть) */}
        {inspections.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-400" />
              Обходы ({inspections.length})
            </h2>
            <div className="space-y-2">
              {inspections.map((insp) => (
                <button
                  key={insp.id}
                  onClick={() => navigate(`/inspections/${insp.id}`)} data-prefetch={`/inspections/${insp.id}`}
                  className="w-full text-left p-3 rounded-lg border border-gray-200 hover:border-primary-300 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-gray-800">
                        {insp.inspector?.full_name ?? 'Инспектор'}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {new Date(insp.created_at).toLocaleDateString('ru')} • {insp.type}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`badge text-xs ${STATUS_COLORS[insp.status] ?? 'bg-gray-100'}`}>
                        {STATUS_LABELS[insp.status] ?? insp.status}
                      </span>
                      <Eye className="w-4 h-4 text-gray-300" />
                    </div>
                  </div>
                  {insp.reviewed_by && (
                    <div className="text-xs text-amber-600 mt-1">
                      ✓ Проверен: {insp.reviewed_by.full_name}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Кнопка снизу */}
      <div className="p-4 bg-white border-t shrink-0">
        {isReviewerOrAdmin ? (
          <p className="text-center text-sm text-gray-400">Проверяющий не проводит обходы — выберите обход выше для проверки</p>
        ) : (
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="btn-primary w-full py-3 text-base flex items-center justify-center gap-2"
          >
            <Play className="w-5 h-5" />
            {startMutation.isPending ? 'Создание обхода...' : 'Начать обход'}
          </button>
        )}
      </div>
    </div>
  )
}
