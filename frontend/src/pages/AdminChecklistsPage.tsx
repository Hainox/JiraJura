import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { checklistsApi } from '@/lib/api'
import type { ChecklistTemplateOut, ChecklistItemOut } from '@/types'
import { ArrowLeft, Pencil, Plus, RotateCcw, EyeOff } from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import { guardDemoAction } from '@/stores/demoMode'

const ISSUE_CATEGORIES = [
  'Оборудование', 'Покрытие', 'Ограждения', 'МАФ', 'Санитарное состояние',
  'Безопасность', 'Документация', 'Освещение', 'Прочее',
]

export default function AdminChecklistsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: templates } = useQuery<ChecklistTemplateOut[]>({
    queryKey: ['checklist-templates-admin'],
    queryFn: checklistsApi.listAdminTemplates,
  })
  const [templateId, setTemplateId] = useState<string | null>(null)
  const activeTemplate = templates?.find((t) => t.id === templateId) ?? templates?.[0]

  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ category: '', question: '', sort_order: 0, is_critical: false, requires_photo: false })
  const [showAdd, setShowAdd] = useState(false)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['checklist-templates-admin'] })

  const createMutation = useMutation({
    mutationFn: () => checklistsApi.createItem({ template_id: activeTemplate!.id, ...form }),
    onSuccess: () => { toast.success('Пункт добавлен'); setShowAdd(false); resetForm(); invalidate() },
    onError: () => toast.error('Не удалось добавить пункт'),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ChecklistItemOut> }) => checklistsApi.updateItem(id, data),
    onSuccess: () => { toast.success('Сохранено'); setEditingId(null); invalidate() },
    onError: () => toast.error('Не удалось сохранить'),
  })

  const resetForm = () => setForm({ category: '', question: '', sort_order: 0, is_critical: false, requires_photo: false })
  const startEdit = (item: ChecklistItemOut) => {
    setEditingId(item.id)
    setForm({ category: item.category ?? '', question: item.question, sort_order: item.sort_order, is_critical: item.is_critical, requires_photo: item.requires_photo })
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate('/admin')} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="font-bold text-lg">Чек-листы</h1>
          <p className="text-blue-200 text-xs">Пункты проверки по типам площадок</p>
        </div>
      </div>

      <div className="flex bg-white border-b px-4 py-2 gap-2 shrink-0">
        {templates?.map((t) => (
          <button
            key={t.id}
            onClick={() => setTemplateId(t.id)}
            className={`flex-1 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              activeTemplate?.id === t.id ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-600'
            }`}
          >
            {t.name}
          </button>
        ))}
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-2">
        {activeTemplate?.items.map((item) => (
          <div key={item.id} className={`card ${!item.is_active ? 'opacity-50' : ''}`}>
            {editingId === item.id ? (
              <div className="space-y-2">
                <select className="input-field text-sm w-full" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  <option value="">Выберите категорию</option>
                  {ISSUE_CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
                </select>
                <textarea className="input-field text-sm w-full" rows={2} placeholder="Текст пункта" value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
                <div className="flex gap-3 flex-wrap text-sm">
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={form.is_critical} onChange={(e) => setForm({ ...form, is_critical: e.target.checked })} />
                    Критичный
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={form.requires_photo} onChange={(e) => setForm({ ...form, requires_photo: e.target.checked })} />
                    Требует фото
                  </label>
                  <label className="flex items-center gap-1.5">
                    Порядок:
                    <input type="number" className="input-field text-sm w-16 py-1" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: parseInt(e.target.value) || 0 })} />
                  </label>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => guardDemoAction(() => updateMutation.mutate({ id: item.id, data: form }))}
                    disabled={!form.question.trim() || updateMutation.isPending}
                    className="btn-primary text-sm px-3 flex-1"
                  >
                    Сохранить
                  </button>
                  <button onClick={() => setEditingId(null)} className="btn-outline text-sm px-3 flex-1">Отмена</button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs text-gray-400 uppercase font-semibold">{item.category || 'Общее'}</div>
                  <div className="text-sm text-gray-800 mt-0.5">{item.question}</div>
                  <div className="flex gap-1.5 mt-1.5 flex-wrap">
                    {item.is_critical && <span className="badge badge-nok text-[10px]">критичный</span>}
                    {item.requires_photo && <span className="badge bg-blue-100 text-blue-700 text-[10px]">фото</span>}
                    {!item.is_active && <span className="badge bg-gray-200 text-gray-600 text-[10px]">отключён</span>}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => startEdit(item)} className="p-2 rounded-lg hover:bg-gray-100" title="Изменить">
                    <Pencil className="w-4 h-4 text-gray-500" />
                  </button>
                  {item.is_active ? (
                    <button
                      onClick={() => { if (confirm(`Отключить пункт «${item.question}»? Он перестанет появляться в новых обходах, но сохранится в истории.`)) guardDemoAction(() => updateMutation.mutate({ id: item.id, data: { is_active: false } })) }}
                      className="p-2 rounded-lg hover:bg-gray-100"
                      title="Отключить"
                    >
                      <EyeOff className="w-4 h-4 text-gray-500" />
                    </button>
                  ) : (
                    <button onClick={() => guardDemoAction(() => updateMutation.mutate({ id: item.id, data: { is_active: true } }))} className="p-2 rounded-lg hover:bg-gray-100" title="Включить обратно">
                      <RotateCcw className="w-4 h-4 text-gray-500" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {showAdd ? (
          <div className="card">
            <div className="space-y-2">
              <select className="input-field text-sm w-full" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  <option value="">Выберите категорию</option>
                  {ISSUE_CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
                </select>
              <textarea className="input-field text-sm w-full" rows={2} placeholder="Текст пункта" value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
              <div className="flex gap-3 flex-wrap text-sm">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={form.is_critical} onChange={(e) => setForm({ ...form, is_critical: e.target.checked })} />
                  Критичный
                </label>
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={form.requires_photo} onChange={(e) => setForm({ ...form, requires_photo: e.target.checked })} />
                  Требует фото
                </label>
              </div>
              <div className="flex gap-2">
                <button onClick={() => createMutation.mutate()} disabled={!form.question.trim() || createMutation.isPending} className="btn-primary text-sm px-3 flex-1">Добавить</button>
                <button onClick={() => { setShowAdd(false); resetForm() }} className="btn-outline text-sm px-3 flex-1">Отмена</button>
              </div>
            </div>
          </div>
        ) : (
          <button onClick={() => { setShowAdd(true); resetForm() }} className="btn-outline w-full py-2.5 text-sm flex items-center justify-center gap-1.5">
            <Plus className="w-4 h-4" /> Добавить пункт
          </button>
        )}
      </div>
    </div>
  )
}
