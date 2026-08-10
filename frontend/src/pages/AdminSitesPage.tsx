import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { districtsApi, courtyardsApi, sitesApi } from '@/lib/api'
import type { DistrictAdminOut, CourtyardAdminOut, SiteOut } from '@/types'
import { ArrowLeft, Merge, Pencil, Search } from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const CHILD_TYPE = 'Детская площадка'
const SPORT_TYPE = 'Спортивная площадка'

export default function AdminSitesPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<'districts' | 'courtyards' | 'sites'>('districts')

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Районы и площадки</h1>
          <p className="text-blue-200 text-xs">Управление данными округа</p>
        </div>
      </div>

      <div className="flex bg-white border-b px-4 py-2 gap-2 shrink-0">
        {[
          { key: 'districts', label: 'Районы' },
          { key: 'courtyards', label: 'Дворы' },
          { key: 'sites', label: 'Площадки' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as typeof tab)}
            className={`flex-1 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              tab === t.key ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="overflow-y-auto flex-1 p-4">
        {tab === 'districts' && <DistrictsTab />}
        {tab === 'courtyards' && <CourtyardsTab />}
        {tab === 'sites' && <SitesTab />}
      </div>
    </div>
  )
}

function DistrictsTab() {
  const queryClient = useQueryClient()
  const { data: districts } = useQuery<DistrictAdminOut[]>({ queryKey: ['districts-admin'], queryFn: districtsApi.listAdmin })
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [merging, setMerging] = useState<string | null>(null)
  const [mergeTarget, setMergeTarget] = useState('')

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['districts-admin'] })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => districtsApi.rename(id, name),
    onSuccess: () => { toast.success('Район переименован'); setRenaming(null); invalidate() },
    onError: () => toast.error('Не удалось переименовать (возможно, такое название уже есть)'),
  })
  const mergeMutation = useMutation({
    mutationFn: ({ id, into }: { id: string; into: string }) => districtsApi.merge(id, into),
    onSuccess: () => { toast.success('Районы объединены'); setMerging(null); invalidate() },
    onError: () => toast.error('Не удалось объединить районы'),
  })

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 mb-2">
        «Объединить с...» переносит все дворы и площадки в выбранный район и удаляет текущий —
        так чинятся задвоенные/битые районы вроде «Район1;Район2», попавшие в базу при импорте KML.
      </p>
      {districts?.map((d) => (
        <div key={d.id} className="card">
          {renaming === d.id ? (
            <div className="flex gap-2">
              <input className="input-field text-sm flex-1" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} autoFocus />
              <button onClick={() => renameMutation.mutate({ id: d.id, name: renameValue })} disabled={!renameValue.trim() || renameMutation.isPending} className="btn-primary text-sm px-3">Сохранить</button>
              <button onClick={() => setRenaming(null)} className="btn-outline text-sm px-3">Отмена</button>
            </div>
          ) : merging === d.id ? (
            <div className="flex gap-2">
              <select className="input-field text-sm flex-1" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
                <option value="">Объединить с районом...</option>
                {districts.filter((x) => x.id !== d.id).map((x) => (
                  <option key={x.id} value={x.id}>{x.name}</option>
                ))}
              </select>
              <button
                onClick={() => { if (confirm(`Перенести все дворы/площадки из «${d.name}» в выбранный район и удалить «${d.name}»?`)) mergeMutation.mutate({ id: d.id, into: mergeTarget }) }}
                disabled={!mergeTarget || mergeMutation.isPending}
                className="btn-primary text-sm px-3"
              >
                Объединить
              </button>
              <button onClick={() => setMerging(null)} className="btn-outline text-sm px-3">Отмена</button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium text-gray-800 truncate">{d.name}</div>
                <div className="text-xs text-gray-500 mt-0.5">Дворов: {d.courtyards_count} · Площадок: {d.sites_count}</div>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={() => { setRenaming(d.id); setRenameValue(d.name) }} className="p-2 rounded-lg hover:bg-gray-100" title="Переименовать">
                  <Pencil className="w-4 h-4 text-gray-500" />
                </button>
                <button onClick={() => { setMerging(d.id); setMergeTarget('') }} className="p-2 rounded-lg hover:bg-gray-100" title="Объединить с другим районом">
                  <Merge className="w-4 h-4 text-gray-500" />
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function CourtyardsTab() {
  const queryClient = useQueryClient()
  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })
  const [districtFilter, setDistrictFilter] = useState('')
  const [search, setSearch] = useState('')
  const { data: courtyards } = useQuery<CourtyardAdminOut[]>({
    queryKey: ['courtyards-admin', districtFilter, search],
    queryFn: () => courtyardsApi.list({ district_id: districtFilter || undefined, search: search || undefined }),
  })
  const [editing, setEditing] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editDistrict, setEditDistrict] = useState('')

  const updateMutation = useMutation({
    mutationFn: ({ id, name, district_id }: { id: string; name: string; district_id: string }) =>
      courtyardsApi.update(id, { name, district_id }),
    onSuccess: () => {
      toast.success('Двор обновлён')
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['courtyards-admin'] })
    },
    onError: () => toast.error('Не удалось сохранить (возможно, такой двор уже есть в этом районе)'),
  })

  return (
    <div className="space-y-2">
      <div className="flex gap-2 mb-2">
        <select className="input-field text-sm flex-1" value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)}>
          <option value="">Все районы</option>
          {districts?.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
        </select>
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input className="input-field text-sm pl-8 w-full" placeholder="Поиск по названию" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>
      {courtyards?.map((c) => (
        <div key={c.id} className="card">
          {editing === c.id ? (
            <div className="space-y-2">
              <input className="input-field text-sm w-full" value={editName} onChange={(e) => setEditName(e.target.value)} autoFocus />
              <select className="input-field text-sm w-full" value={editDistrict} onChange={(e) => setEditDistrict(e.target.value)}>
                {districts?.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
              </select>
              <div className="flex gap-2">
                <button onClick={() => updateMutation.mutate({ id: c.id, name: editName, district_id: editDistrict })} disabled={!editName.trim() || updateMutation.isPending} className="btn-primary text-sm px-3 flex-1">Сохранить</button>
                <button onClick={() => setEditing(null)} className="btn-outline text-sm px-3 flex-1">Отмена</button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium text-gray-800 truncate">{c.name}</div>
                <div className="text-xs text-gray-500 mt-0.5">{c.district_name} · Площадок: {c.sites_count}</div>
              </div>
              <button onClick={() => { setEditing(c.id); setEditName(c.name); setEditDistrict(c.district_id) }} className="p-2 rounded-lg hover:bg-gray-100 shrink-0" title="Изменить">
                <Pencil className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          )}
        </div>
      ))}
      {courtyards?.length === 0 && <div className="text-center text-gray-400 py-8">Ничего не найдено</div>}
    </div>
  )
}

function SitesTab() {
  const queryClient = useQueryClient()
  const { data: districts } = useQuery({ queryKey: ['districts'], queryFn: districtsApi.list })
  const [districtFilter, setDistrictFilter] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const { data: sitesData } = useQuery({
    queryKey: ['sites-admin', districtFilter, showInactive],
    queryFn: () => sitesApi.list({ district_id: districtFilter || undefined, include_inactive: showInactive, page_size: 500 }),
    enabled: !!districtFilter,
  })
  const [editing, setEditing] = useState<string | null>(null)
  const [editType, setEditType] = useState('')
  const [editArea, setEditArea] = useState('')
  const [editActive, setEditActive] = useState(true)

  const updateMutation = useMutation({
    mutationFn: ({ id, type, area_m2, is_active }: { id: string; type: string; area_m2: number; is_active: boolean }) =>
      sitesApi.update(id, { type, area_m2, is_active }),
    onSuccess: () => {
      toast.success('Площадка обновлена')
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['sites-admin'] })
    },
    onError: () => toast.error('Не удалось сохранить'),
  })

  return (
    <div className="space-y-2">
      <div className="flex gap-2 mb-2 items-center">
        <select className="input-field text-sm flex-1" value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)}>
          <option value="">Выберите район</option>
          {districts?.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 shrink-0 whitespace-nowrap">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          С отключёнными
        </label>
      </div>
      {!districtFilter && <div className="text-center text-gray-400 py-8">Выберите район, чтобы увидеть площадки</div>}
      {sitesData?.items.map((s: SiteOut) => (
        <div key={s.id} className={`card ${!s.is_active ? 'opacity-60' : ''}`}>
          {editing === s.id ? (
            <div className="space-y-2">
              <select className="input-field text-sm w-full" value={editType} onChange={(e) => setEditType(e.target.value)}>
                <option value={CHILD_TYPE}>Детская площадка</option>
                <option value={SPORT_TYPE}>Спортивная площадка</option>
              </select>
              <input type="number" step="0.01" className="input-field text-sm w-full" value={editArea} onChange={(e) => setEditArea(e.target.value)} placeholder="Площадь, м²" />
              <label className="flex items-center gap-1.5 text-sm text-gray-700">
                <input type="checkbox" checked={editActive} onChange={(e) => setEditActive(e.target.checked)} />
                Активна (видна на карте/в списке)
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => updateMutation.mutate({ id: s.id, type: editType, area_m2: parseFloat(editArea), is_active: editActive })}
                  disabled={!editArea || updateMutation.isPending}
                  className="btn-primary text-sm px-3 flex-1"
                >
                  Сохранить
                </button>
                <button onClick={() => setEditing(null)} className="btn-outline text-sm px-3 flex-1">Отмена</button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium text-gray-800 truncate">{s.courtyard?.name ?? 'Площадка'}</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {s.type === CHILD_TYPE ? 'Детская' : 'Спортивная'} · {s.area_m2} м²
                  {!s.is_active && <span className="text-red-500 ml-1">· отключена</span>}
                </div>
              </div>
              <button
                onClick={() => { setEditing(s.id); setEditType(s.type); setEditArea(String(s.area_m2)); setEditActive(s.is_active) }}
                className="p-2 rounded-lg hover:bg-gray-100 shrink-0"
                title="Изменить"
              >
                <Pencil className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          )}
        </div>
      ))}
      {districtFilter && sitesData?.items.length === 0 && <div className="text-center text-gray-400 py-8">Нет площадок</div>}
    </div>
  )
}
