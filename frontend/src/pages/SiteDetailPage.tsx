import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { sitesApi, inspectionsApi, checklistsApi } from '@/lib/api'
import type { SiteOut, ChecklistTemplateOut } from '@/types'
import { ArrowLeft, Play } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SiteDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const siteId = id!

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

  const startMutation = useMutation({
    mutationFn: () => inspectionsApi.create(siteId),
    onSuccess: (inspection) => {
      toast.success('Обход начат!')
      navigate(`/inspections/${inspection.id}`)
    },
    onError: () => toast.error('Ошибка при создании обхода'),
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
        <button onClick={() => navigate('/')} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-lg truncate">{site.courtyard?.name ?? 'Площадка'}</h1>
          <p className="text-blue-200 text-xs truncate">
            {site.district?.name ?? 'Район не указан'}
          </p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* Инфо-карточка */}
        <div className="card">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-gray-400 text-xs">Тип</div>
              <div className="font-medium mt-0.5">
                {site.type === 'children' ? 'Детская площадка' : 'Спортивная площадка'}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-xs">Площадь</div>
              <div className="font-medium mt-0.5">{site.area_m2} м²</div>
            </div>
            <div className="col-span-2">
              <div className="text-gray-400 text-xs">Район</div>
              <div className="font-medium mt-0.5">{site.district?.name}</div>
            </div>
          </div>
        </div>

        {/* Чек-лист предпросмотр */}
        {checklists && checklists.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-gray-800 mb-3">Чек-лист обхода</h2>
            {checklists.map((tmpl) => (
              <div key={tmpl.id} className="mb-3 last:mb-0">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1.5">
                  {tmpl.name}
                </div>
                <div className="space-y-1.5">
                  {tmpl.items.map((item) => (
                    <div key={item.id} className="text-sm text-gray-700 flex items-start gap-2">
                      <span className="text-gray-300 mt-0.5">•</span>
                      <span>{item.question}</span>
                      {item.is_critical && (
                        <span className="badge badge-nok shrink-0 text-[10px]">важно</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Кнопка старта */}
      <div className="p-4 bg-white border-t shrink-0">
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="btn-primary w-full py-3 text-base flex items-center justify-center gap-2"
        >
          <Play className="w-5 h-5" />
          {startMutation.isPending ? 'Создание обхода...' : 'Начать обход'}
        </button>
      </div>
    </div>
  )
}
