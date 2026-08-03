import { useState, useMemo, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { inspectionsApi, checklistsApi, issuesApi } from '@/lib/api'
import type { InspectionOut, ChecklistTemplateOut, ChecklistItemOut, ChecklistAnswerOut, PhotoOut } from '@/types'
import {
  ArrowLeft, Send, X, AlertTriangle,
  CheckCircle2, HelpCircle, ChevronRight, Plus, Camera, Image
} from 'lucide-react'
import toast from 'react-hot-toast'

type AnswerResult = 'ok' | 'defect' | 'pending'

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const inspectionId = id!

  const [answers, setAnswers] = useState<Record<string, { result: AnswerResult; comment: string }>>({})
  const [activeItemId, setActiveItemId] = useState<string | null>(null)
  const [showIssueForm, setShowIssueForm] = useState(false)
  const [issueTitle, setIssueTitle] = useState('')
  const [issueDesc, setIssueDesc] = useState('')
  const [issueCriticality, setIssueCriticality] = useState('medium')
  const [photos, setPhotos] = useState<PhotoOut[]>([])
  const [showPhotoPanel, setShowPhotoPanel] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: inspection, isLoading } = useQuery<InspectionOut>({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  // Загружаем чек-лист по типу площадки
  const { data: checklists } = useQuery<ChecklistTemplateOut[]>({
    queryKey: ['checklist-template', inspection?.site?.type],
    queryFn: () => checklistsApi.template({ site_type: inspection!.site.type }),
    enabled: !!inspection?.site?.type,
  })

  const allItems: ChecklistItemOut[] = useMemo(
    () => checklists?.flatMap((tmpl) => tmpl.items) ?? [],
    [checklists]
  )

  // Инициализируем ответы из существующих
  useEffect(() => {
    if (inspection?.answers) {
      const existing: Record<string, { result: AnswerResult; comment: string }> = {}
      for (const a of inspection.answers) {
        existing[a.checklist_item_id] = {
          result: (a.result === 'ok' ? 'ok' : a.result === 'defect' ? 'defect' : 'pending') as AnswerResult,
          comment: a.comment ?? '',
        }
      }
      setAnswers((prev) => ({ ...existing, ...prev }))
    }
    if (inspection?.photos) {
      setPhotos(inspection.photos)
    }
  }, [inspection?.answers, inspection?.photos])

  const saveMutation = useMutation({
    mutationFn: () => {
      const answerList = Object.entries(answers)
        .filter(([, a]) => a.result !== 'pending')
        .map(([itemId, a]) => ({
          checklist_item_id: itemId,
          result: a.result,
          comment: a.comment || undefined,
        }))
      return inspectionsApi.update(inspectionId, { answers: answerList })
    },
    onSuccess: () => {
      toast.success('Сохранено')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
    },
    onError: () => toast.error('Ошибка сохранения'),
  })

  const createIssueMutation = useMutation({
    mutationFn: () =>
      issuesApi.create({
        inspection_id: inspectionId,
        title: issueTitle,
        description: issueDesc || undefined,
        criticality: issueCriticality,
      }),
    onSuccess: () => {
      toast.success('Замечание создано')
      setShowIssueForm(false)
      setIssueTitle('')
      setIssueDesc('')
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: () => toast.error('Ошибка создания замечания'),
  })

  const uploadPhotoMutation = useMutation({
    mutationFn: (file: File) => inspectionsApi.uploadPhoto(inspectionId, file),
    onSuccess: (photo) => {
      setPhotos((prev) => [...prev, photo])
      toast.success('Фото загружено')
    },
    onError: () => toast.error('Ошибка загрузки фото'),
  })

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadPhotoMutation.mutate(file)
      e.target.value = '' // сброс для повторной загрузки того же файла
    }
  }

  const handleMark = (itemId: string, result: AnswerResult) => {
    if (result === 'pending') return
    setAnswers((prev) => ({
      ...prev,
      [itemId]: { result, comment: prev[itemId]?.comment ?? '' },
    }))
    if (result === 'defect') setActiveItemId(itemId)
  }

  const handleComment = (itemId: string, comment: string) => {
    setAnswers((prev) => ({
      ...prev,
      [itemId]: { ...(prev[itemId] ?? { result: 'pending' }), comment },
    }))
  }

  const getStatusIcon = (itemId: string) => {
    const a = answers[itemId]
    if (!a || a.result === 'pending') return <HelpCircle className="w-4 h-4 text-gray-300" />
    if (a.result === 'ok') return <CheckCircle2 className="w-4 h-4 text-green-500" />
    return <AlertTriangle className="w-4 h-4 text-red-500" />
  }

  const stats = useMemo(() => {
    const total = allItems.length
    const ok = Object.values(answers).filter((a) => a.result === 'ok').length
    const nok = Object.values(answers).filter((a) => a.result === 'defect').length
    return { total, ok, nok, pending: total - ok - nok }
  }, [allItems, answers])

  const activeItem = allItems.find((it) => it.id === activeItemId)

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Загрузка...</div>
      </div>
    )
  }

  if (!inspection) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Обход не найден</div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate(`/sites/${inspection.site_id}`)} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-lg truncate">{inspection.site?.courtyard?.name ?? 'Обход'}</h1>
          <div className="flex gap-3 text-xs text-blue-200 mt-0.5">
            <span>✓ {stats.ok}</span>
            <span>✕ {stats.nok}</span>
            <span>? {stats.pending}</span>
          </div>
        </div>
        <button onClick={() => saveMutation.mutate()} className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30">
          Сохранить
        </button>
        <button
          onClick={() => setShowPhotoPanel((v) => !v)}
          className={`text-xs px-3 py-1.5 rounded-lg ${
            showPhotoPanel ? 'bg-white/30' : 'bg-white/20 hover:bg-white/30'
          }`}
        >
          <Camera className="w-4 h-4 inline mr-1" />
          {photos.length > 0 ? photos.length : ''}
        </button>
      </div>

      {/* Панель фото */}
      {showPhotoPanel && (
        <div className="bg-white border-b p-3 shrink-0">
          <div className="flex flex-wrap gap-2 mb-2">
            {photos.map((p) => (
              <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                <img
                  src={p.url}
                  alt=""
                  className="w-16 h-16 object-cover rounded-lg border"
                />
              </a>
            ))}
            {photos.length === 0 && (
              <div className="text-xs text-gray-400 py-2">Нет фотографий. Нажмите «Добавить».</div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={handlePhotoUpload}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadPhotoMutation.isPending}
            className="btn-outline py-1.5 px-3 text-sm"
          >
            <Camera className="w-4 h-4 inline mr-1" />
            {uploadPhotoMutation.isPending ? 'Загрузка...' : 'Добавить фото'}
          </button>
        </div>
      )}

      {/* Прогресс-бар */}
      <div className="h-1 bg-gray-200 shrink-0">
        <div
          className="h-full bg-green-500 transition-all duration-300"
          style={{ width: `${stats.total > 0 ? ((stats.ok + stats.nok) / stats.total) * 100 : 0}%` }}
        />
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-3">
        {allItems.map((item) => (
          <div
            key={item.id}
            className={`card transition-colors ${
              activeItemId === item.id ? 'border-primary-400 ring-2 ring-primary-100' : ''
            }`}
          >
            <div className="flex items-start gap-3">
              {getStatusIcon(item.id)}
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-400 uppercase font-semibold">
                  {item.category ?? 'Общее'}
                </div>
                <div className="text-sm text-gray-800 mt-0.5">{item.question}</div>

                {(answers[item.id]?.result && answers[item.id]?.result !== 'pending') && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className={`badge ${answers[item.id]?.result === 'ok' ? 'badge-ok' : 'badge-nok'}`}>
                      {answers[item.id]?.result === 'ok' ? 'В порядке' : 'Нарушение'}
                    </span>
                    {answers[item.id]?.comment && (
                      <span className="text-xs text-gray-500 truncate">{answers[item.id]?.comment}</span>
                    )}
                  </div>
                )}
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-1" />
            </div>

            {/* Кнопки оценки */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => handleMark(item.id, 'ok')}
                className={`flex-1 py-2 text-sm rounded-lg font-medium transition-all ${
                  answers[item.id]?.result === 'ok'
                    ? 'bg-green-500 text-white'
                    : 'bg-green-50 text-green-700 hover:bg-green-100'
                }`}
              >
                ✓ ОК
              </button>
              <button
                onClick={() => handleMark(item.id, 'defect')}
                className={`flex-1 py-2 text-sm rounded-lg font-medium transition-all ${
                  answers[item.id]?.result === 'defect'
                    ? 'bg-red-500 text-white'
                    : 'bg-red-50 text-red-700 hover:bg-red-100'
                }`}
              >
                ✕ Не ОК
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Нижняя панель */}
      {activeItem && (
        <div className="bg-white border-t p-4 shrink-0 max-h-[40vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-gray-800 truncate flex-1">
              {activeItem.question}
            </h3>
            <button onClick={() => setActiveItemId(null)} className="p-1 hover:bg-gray-100 rounded-lg">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>

          <textarea
            className="input-field mb-3 text-sm"
            rows={2}
            placeholder="Комментарий..."
            value={answers[activeItem.id]?.comment ?? ''}
            onChange={(e) => handleComment(activeItem.id, e.target.value)}
          />

          {!showIssueForm ? (
            <button onClick={() => setShowIssueForm(true)} className="btn-outline w-full py-2 text-sm">
              <Plus className="w-4 h-4 inline mr-1" />
              Создать замечание
            </button>
          ) : (
            <div className="space-y-2">
              <input
                className="input-field text-sm"
                placeholder="Заголовок замечания"
                value={issueTitle}
                onChange={(e) => setIssueTitle(e.target.value)}
              />
              <textarea
                className="input-field text-sm"
                rows={2}
                placeholder="Описание (необязательно)"
                value={issueDesc}
                onChange={(e) => setIssueDesc(e.target.value)}
              />
              <div className="flex gap-2">
                <select
                  className="input-field text-sm flex-1"
                  value={issueCriticality}
                  onChange={(e) => setIssueCriticality(e.target.value)}
                >
                  <option value="low">Низкая</option>
                  <option value="medium">Средняя</option>
                  <option value="high">Высокая</option>
                  <option value="critical">Критическая</option>
                </select>
                <button
                  onClick={() => { if (issueTitle.trim()) createIssueMutation.mutate() }}
                  disabled={!issueTitle.trim()}
                  className="btn-primary py-2 px-4 text-sm"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
