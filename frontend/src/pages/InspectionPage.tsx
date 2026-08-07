import { useState, useMemo, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { inspectionsApi, checklistsApi, issuesApi, reportsApi } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { InspectionOut, ChecklistTemplateOut, ChecklistItemOut, PhotoOut } from '@/types'
import {
  ArrowLeft, Send, X, AlertTriangle, CheckCircle, Eye,
  CheckCircle2, HelpCircle, ChevronRight, Plus, Camera,
  Flag, RotateCcw, FileText
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'

type AnswerResult = 'ok' | 'defect' | 'pending'

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе',
  completed: 'Завершён', issues_found: 'Есть нарушения', critical: 'Критический',
}

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const inspectionId = id!
  const user = useAuthStore((s) => s.user)

  const [answers, setAnswers] = useState<Record<string, { result: AnswerResult; comment: string }>>({})
  const [activeItemId, setActiveItemId] = useState<string | null>(null)
  const [showIssueForm, setShowIssueForm] = useState(false)
  const [issueTitle, setIssueTitle] = useState('')
  const [issueDesc, setIssueDesc] = useState('')
  const [issueCriticality, setIssueCriticality] = useState('medium')
  const [photos, setPhotos] = useState<PhotoOut[]>([])
  const [showPhotoPanel, setShowPhotoPanel] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const itemFileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingForItemId, setUploadingForItemId] = useState<string | null>(null)
  // Замечание, для которого сейчас предлагаем прикрепить фото сразу после
  // создания — свои фото, а не общий фотоальбом обхода
  const [issuePhotoTargetId, setIssuePhotoTargetId] = useState<string | null>(null)
  const [issuePhotoCount, setIssuePhotoCount] = useState(0)
  const issuePhotoInputRef = useRef<HTMLInputElement>(null)

  // Reviewer state
  const [reviewerComment, setReviewerComment] = useState('')
  const [showReviewPanel, setShowReviewPanel] = useState(false)
  const [showCompleteConfirm, setShowCompleteConfirm] = useState(false)

  const { data: inspection, isLoading } = useQuery<InspectionOut>({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  const isInspector = user?.id === inspection?.inspector?.id
  const isReviewer = user?.role === 'reviewer' || user?.role === 'admin'
  // !isInspector, не "isReviewer && !isInspector" — иначе любой ДРУГОЙ
  // инспектор (не владелец обхода и не проверяющий/админ) видел чек-лист
  // полностью редактируемым и мог реально создавать замечания на чужом
  // обходе (открыв URL /inspections/:id с чужим id)
  const isReadOnly = !isInspector

  // Is this inspection returned for revision?
  const isRevision = inspection?.status === 'in_progress' && !!inspection?.reviewer_comment && isInspector

  const { data: checklists } = useQuery<ChecklistTemplateOut[]>({
    queryKey: ['checklist-template', inspection?.site?.type],
    queryFn: () => checklistsApi.template({ site_type: inspection!.site.type }),
    enabled: !!inspection?.site?.type,
  })

  const allItems: ChecklistItemOut[] = useMemo(
    () => checklists?.flatMap((tmpl) => tmpl.items) ?? [],
    [checklists]
  )

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
    // reviewerComment НЕ подставляем из inspection.reviewer_comment — иначе
    // при повторной проверке поле молча предзаполняется прошлым "вернуть
    // на доработку" комментарием, и "✓ Принять" без единой правки заново
    // отправляет тот же устаревший текст, из-за чего он никогда не
    // очищается. Прошлый комментарий и так виден отдельным read-only
    // блоком ("Предыдущий комментарий") — редактируемое поле начинается
    // пустым каждый раз.
  }, [inspection?.answers, inspection?.photos, inspection?.reviewer_comment])

  const generalPhotos = useMemo(
    () => photos.filter((p) => p.target_type === 'inspection'),
    [photos]
  )
  const photosByAnswer = useMemo(() => {
    const map: Record<string, PhotoOut[]> = {}
    for (const p of photos) {
      if (p.target_type === 'checklist_answer' && p.checklist_answer_id) {
        const answer = inspection?.answers?.find((a) => a.id === p.checklist_answer_id)
        if (answer) {
          const key = answer.checklist_item_id
          if (!map[key]) map[key] = []
          map[key].push(p)
        }
      }
    }
    return map
  }, [photos, inspection?.answers])

  // Пункты чек-листа с requires_photo (например «Фото общего вида
  // площадки») были помечены обязательными к фото ещё в schema.sql, но это
  // никогда не проверялось — обход завершался вообще без этих фото. Как и
  // с общим фото объекта, блокируем только уже отмеченные пункты — чтобы
  // не мешать завершению с обычными "не проверено" пунктами.
  const missingRequiredPhotoItems = useMemo(
    () => allItems.filter((item) => {
      if (!item.requires_photo) return false
      const a = answers[item.id]
      if (!a || a.result === 'pending') return false
      return (photosByAnswer[item.id] ?? []).length === 0
    }),
    [allItems, answers, photosByAnswer]
  )

  const buildAnswerList = () =>
    Object.entries(answers)
      .filter(([, a]) => a.result !== 'pending')
      .map(([itemId, a]) => ({
        checklist_item_id: itemId,
        result: a.result,
        comment: a.comment || undefined,
      }))

  const saveMutation = useMutation({
    mutationFn: () => inspectionsApi.update(inspectionId, { answers: buildAnswerList() }),
    onSuccess: () => {
      toast.success('Сохранено')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
    },
    onError: () => toast.error('Ошибка сохранения'),
  })

  const reviewMutation = useMutation({
    mutationFn: (data: { status: string; reviewer_comment?: string }) =>
      inspectionsApi.update(inspectionId, data),
    onSuccess: () => {
      toast.success('Проверено')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
      setShowReviewPanel(false)
    },
    onError: () => toast.error('Ошибка'),
  })

  const completeMutation = useMutation({
    // Завершение — тот же PATCH, что и «Сохранить», но с добавленным status:
    // если отправить только status, набранные ответы чек-листа, ещё не
    // сохранённые отдельным «Сохранить», молча теряются на сервере
    mutationFn: (result: 'completed' | 'issues_found') =>
      inspectionsApi.update(inspectionId, { status: result, answers: buildAnswerList() }),
    onSuccess: () => {
      toast.success('Обход завершён')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
      navigate(`/sites/${inspection!.site_id}`)
    },
    onError: () => toast.error('Ошибка завершения'),
  })

  const returnMutation = useMutation({
    mutationFn: (data: { status: string; reviewer_comment: string }) =>
      inspectionsApi.update(inspectionId, data),
    onSuccess: () => {
      toast.success('Возвращено на доработку')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
      setShowReviewPanel(false)
    },
    onError: () => toast.error('Ошибка'),
  })

  const createIssueMutation = useMutation({
    mutationFn: () =>
      issuesApi.create({
        inspection_id: inspectionId,
        title: issueTitle,
        description: issueDesc || undefined,
        criticality: issueCriticality,
      }),
    onSuccess: (issue) => {
      toast.success('Замечание создано')
      setIssueTitle('')
      setIssueDesc('')
      // не закрываем панель сразу — даём прикрепить фото именно к этому
      // замечанию, а не заставляем грузить его отдельно в общий альбом
      setIssuePhotoTargetId(issue.id)
      setIssuePhotoCount(0)
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: () => toast.error('Ошибка создания замечания'),
  })

  const uploadIssuePhotoMutation = useMutation({
    mutationFn: (file: File) => {
      if (!issuePhotoTargetId) return Promise.reject(new Error('no target issue'))
      return issuesApi.uploadPhoto(issuePhotoTargetId, file)
    },
    onSuccess: () => {
      setIssuePhotoCount((c) => c + 1)
      toast.success('Фото замечания загружено')
    },
    onError: () => toast.error('Ошибка загрузки фото замечания'),
  })

  const finishIssuePhotos = () => {
    setIssuePhotoTargetId(null)
    setIssuePhotoCount(0)
    setShowIssueForm(false)
  }

  const uploadGeneralPhotoMutation = useMutation({
    mutationFn: (file: File) => inspectionsApi.uploadPhoto(inspectionId, file),
    onSuccess: (photo) => {
      setPhotos((prev) => [...prev, photo])
      toast.success('Фото загружено')
    },
    onError: () => toast.error('Ошибка загрузки фото'),
  })

  const uploadItemPhotoMutation = useMutation({
    mutationFn: async ({ file, checklistItemId }: { file: File; checklistItemId: string }) => {
      let answer = inspection?.answers?.find((a) => a.checklist_item_id === checklistItemId)
      if (!answer) {
        // Ответ по этому пункту ещё не сохранён на сервере — без сохранения
        // backend не может связать фото с пунктом чек-листа (checklist_answer_id)
        // и молча положит его как общее фото обхода, оторванное от пункта
        const updated = await inspectionsApi.update(inspectionId, { answers: buildAnswerList() })
        queryClient.setQueryData(['inspection', inspectionId], updated)
        answer = updated.answers?.find((a) => a.checklist_item_id === checklistItemId)
      }
      return inspectionsApi.uploadPhoto(inspectionId, file, answer?.id)
    },
    onSuccess: (photo) => {
      setPhotos((prev) => [...prev, photo])
      setUploadingForItemId(null)
      toast.success('Фото для пункта загружено')
    },
    onError: () => {
      setUploadingForItemId(null)
      toast.error('Ошибка загрузки фото')
    },
  })

  const handleGeneralPhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadGeneralPhotoMutation.mutate(file)
      e.target.value = ''
    }
  }

  const handleItemPhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && uploadingForItemId) {
      uploadItemPhotoMutation.mutate({ file, checklistItemId: uploadingForItemId })
      e.target.value = ''
    }
  }

  const triggerItemUpload = (itemId: string) => {
    setUploadingForItemId(itemId)
    setTimeout(() => itemFileInputRef.current?.click(), 50)
  }

  const handleMark = (itemId: string, result: AnswerResult) => {
    if (isReadOnly || result === 'pending') return
    setAnswers((prev) => ({
      ...prev,
      [itemId]: { result, comment: prev[itemId]?.comment ?? '' },
    }))
    if (result === 'defect') setActiveItemId(itemId)
  }

  const handleComment = (itemId: string, comment: string) => {
    if (isReadOnly) return
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
            {isReadOnly && <span className="opacity-70">| {STATUS_LABELS[inspection.status] ?? inspection.status}</span>}
          </div>
        </div>
        {isInspector && inspection.status === 'in_progress' && (
          <>
            <button onClick={() => saveMutation.mutate()} className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30">
              Сохранить
            </button>
            <button
              onClick={() => setShowCompleteConfirm(true)}
              className="text-xs bg-green-600 px-3 py-1.5 rounded-lg hover:bg-green-700 font-medium"
            >
              <Flag className="w-3.5 h-3.5 inline mr-1" />
              Завершить
            </button>
          </>
        )}
        <button
          onClick={() => setShowPhotoPanel((v) => !v)}
          className={`text-xs px-3 py-1.5 rounded-lg relative ${
            showPhotoPanel ? 'bg-white/30' : generalPhotos.length === 0 && isInspector ? 'bg-red-500/60 hover:bg-red-500/80' : 'bg-white/20 hover:bg-white/30'
          }`}
        >
          <Camera className="w-4 h-4 inline mr-1" />
          {photos.length > 0 ? photos.length : isInspector ? '!' : ''}
        </button>
        <button
          onClick={() => reportsApi.openPdfReport(inspectionId).catch(() => toast.error('Не удалось открыть отчёт'))}
          className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30"
          title="PDF-отчёт"
        >
          <FileText className="w-4 h-4 inline mr-1" />
        </button>
        {isReviewer && !isInspector && inspection.status !== 'planned' && (
          <button
            onClick={() => setShowReviewPanel((v) => !v)}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium ${
              showReviewPanel ? 'bg-amber-500 text-white' : 'bg-white/20 hover:bg-white/30'
            }`}
          >
            <Eye className="w-4 h-4 inline mr-1" />
            Проверить
          </button>
        )}
      </div>

      {/* Revision banner */}
      {isRevision && (
        <div className="bg-orange-50 border-b border-orange-200 px-4 py-2 text-xs text-orange-800">
          <div className="flex items-center gap-2 font-medium mb-0.5">
            <RotateCcw className="w-3.5 h-3.5" />
            Возвращено на доработку
          </div>
          {inspection.reviewer_comment && (
            <div className="text-orange-700">{inspection.reviewer_comment}</div>
          )}
        </div>
      )}

      {/* Reviewer info bar */}
      {inspection.reviewed_by && !isRevision && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-xs text-amber-800 flex items-center gap-2">
          <CheckCircle className="w-3.5 h-3.5" />
          Проверено: {inspection.reviewed_by.full_name}
          {inspection.reviewed_at && `, ${new Date(inspection.reviewed_at).toLocaleDateString('ru')}`}
        </div>
      )}

      {/* Complete confirmation */}
      {showCompleteConfirm && isInspector && (
        <div className="bg-white border-b p-3 shrink-0 space-y-3">
          <div className="text-sm font-semibold text-gray-800">Завершить обход</div>
          <p className="text-xs text-gray-500">
            Проверено ✓{stats.ok} пунктов, выявлено ✕{stats.nok} нарушений.
            {stats.pending > 0 && ` Осталось ${stats.pending} непроверенных.`}
          </p>
          {generalPhotos.length === 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Нет общего фото объекта!</div>
                <div className="text-red-600 mt-0.5">Общее фото площадки обязательно. Нажмите 📷 «Добавить общее фото» в панели выше.</div>
              </div>
            </div>
          )}
          {missingRequiredPhotoItems.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Нужно фото для отмеченных пунктов!</div>
                <div className="text-red-600 mt-0.5">
                  {missingRequiredPhotoItems.map((it) => it.question).join(', ')}
                </div>
              </div>
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => { setShowCompleteConfirm(false) }}
              className="flex-1 py-2 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
            >
              Отмена
            </button>
            <button
              onClick={() => completeMutation.mutate('completed')}
              disabled={completeMutation.isPending || generalPhotos.length === 0 || missingRequiredPhotoItems.length > 0}
              className="flex-1 py-2 text-sm bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-40"
            >
              ✓ Всё в порядке
            </button>
            {stats.nok > 0 && (
              <button
                onClick={() => completeMutation.mutate('issues_found')}
                disabled={completeMutation.isPending || generalPhotos.length === 0 || missingRequiredPhotoItems.length > 0}
                className="flex-1 py-2 text-sm bg-orange-600 text-white rounded-lg font-medium hover:bg-orange-700 disabled:opacity-40"
              >
                ⚠ Завершить с нарушениями
              </button>
            )}
          </div>
        </div>
      )}

      {/* Панель проверяющего */}
      {showReviewPanel && isReviewer && (
        <div className="bg-white border-b p-3 shrink-0 space-y-3">
          <div className="text-sm font-semibold text-gray-800">Проверка обхода</div>
          <textarea
            className="input-field text-sm"
            rows={2}
            placeholder="Комментарий проверяющего..."
            value={reviewerComment}
            onChange={(e) => setReviewerComment(e.target.value)}
          />
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => reviewMutation.mutate({ status: 'completed', reviewer_comment: reviewerComment })}
              disabled={reviewMutation.isPending}
              className="flex-1 py-2 text-sm bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 min-w-[100px]"
            >
              ✓ Принять
            </button>
            <button
              onClick={() => reviewMutation.mutate({ status: 'issues_found', reviewer_comment: reviewerComment })}
              disabled={reviewMutation.isPending}
              className="flex-1 py-2 text-sm bg-orange-600 text-white rounded-lg font-medium hover:bg-orange-700 min-w-[100px]"
            >
              ⚠ Есть нарушения
            </button>
            <button
              onClick={() => reviewMutation.mutate({ status: 'critical', reviewer_comment: reviewerComment })}
              disabled={reviewMutation.isPending}
              className="flex-1 py-2 text-sm bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 min-w-[100px]"
            >
              ✕ Критический
            </button>
          </div>
          <button
            onClick={() => returnMutation.mutate({ status: 'in_progress', reviewer_comment: reviewerComment })}
            disabled={returnMutation.isPending || !reviewerComment.trim()}
            className="w-full py-2 text-sm bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50"
            title="Укажите комментарий для возврата"
          >
            <RotateCcw className="w-4 h-4 inline mr-1" />
            Вернуть на доработку
          </button>
          {inspection.reviewer_comment && !isRevision && (
            <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded">
              Предыдущий комментарий: {inspection.reviewer_comment}
            </div>
          )}
        </div>
      )}

      {/* Панель общих фото */}
      {showPhotoPanel && (
        <div className="bg-white border-b p-3 shrink-0">
          <div className="text-xs text-gray-500 mb-2 font-medium">
            {isReadOnly ? 'Фото обхода' : 'Общие фото обхода'}
          </div>
          <div className="flex flex-wrap gap-2 mb-2">
            {generalPhotos.map((p) => (
              <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                <img src={p.url} alt="" className="w-16 h-16 object-cover rounded-lg border" />
              </a>
            ))}
            {generalPhotos.length === 0 && (
              <div className="text-xs text-gray-400 py-2">Нет фотографий</div>
            )}
          </div>
          {!isReadOnly && (
            <>
              {/* Без capture="environment" — на некоторых Android WebView с
                  ранее заблокированным разрешением на камеру этот атрибут
                  заставлял input молча ничего не делать по тапу (ни диалога,
                  ни ошибки), без фолбэка на выбор из галереи/файлов. Без
                  capture — обычный системный выбор (камера ИЛИ галерея). */}
              <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleGeneralPhotoUpload} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploadGeneralPhotoMutation.isPending} className="btn-outline py-1.5 px-3 text-sm">
                <Camera className="w-4 h-4 inline mr-1" />
                {uploadGeneralPhotoMutation.isPending ? 'Загрузка...' : 'Добавить общее фото'}
              </button>
            </>
          )}
        </div>
      )}

      {/* Скрытый input для загрузки фото пункта */}
      {!isReadOnly && (
        <input ref={itemFileInputRef} type="file" accept="image/*" className="hidden" onChange={handleItemPhotoUpload} />
      )}

      {/* Прогресс-бар */}
      <div className="h-1 bg-gray-200 shrink-0">
        <div
          className="h-full bg-green-500 transition-all duration-300"
          style={{ width: `${stats.total > 0 ? ((stats.ok + stats.nok) / stats.total) * 100 : 0}%` }}
        />
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-3">
        {allItems.map((item) => {
          const itemPhotos = photosByAnswer[item.id] ?? []
          return (
          <div key={item.id} className={`card transition-colors ${activeItemId === item.id ? 'border-primary-400 ring-2 ring-primary-100' : ''}`}>
            <div className="flex items-start gap-3">
              {getStatusIcon(item.id)}
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-400 uppercase font-semibold">{item.category ?? 'Общее'}</div>
                <div className="text-sm text-gray-800 mt-0.5">{item.question}</div>

                {(answers[item.id]?.result && answers[item.id]?.result !== 'pending') && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className={`badge ${answers[item.id]?.result === 'ok' ? 'badge-ok' : 'badge-nok'}`}>
                      {answers[item.id]?.result === 'ok' ? 'В порядке' : 'Нарушение'}
                    </span>
                    {answers[item.id]?.comment && (
                      <span className="text-xs text-gray-500 truncate">{answers[item.id]?.comment}</span>
                    )}
                  </div>
                )}

                {itemPhotos.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {itemPhotos.map((p) => (
                      <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                        <img src={p.url} alt="" className="w-12 h-12 object-cover rounded border" />
                      </a>
                    ))}
                  </div>
                )}

                {!isReadOnly && answers[item.id]?.result === 'defect' && (
                  <div className="mt-2">
                    <button
                      onClick={() => triggerItemUpload(item.id)}
                      disabled={uploadItemPhotoMutation.isPending && uploadingForItemId === item.id}
                      className="w-full py-2.5 rounded-lg font-medium text-sm bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 flex items-center justify-center gap-2 disabled:opacity-60"
                    >
                      <Camera className="w-4 h-4" />
                      {uploadItemPhotoMutation.isPending && uploadingForItemId === item.id ? 'Загрузка...' : 'Добавить фото дефекта'}
                    </button>
                  </div>
                )}
              </div>
              {!isReadOnly && <ChevronRight className="w-4 h-4 text-gray-300 shrink-0 mt-1" />}
            </div>

            {!isReadOnly && (
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => handleMark(item.id, 'ok')}
                  className={`flex-1 py-2 text-sm rounded-lg font-medium transition-all ${
                    answers[item.id]?.result === 'ok' ? 'bg-green-500 text-white' : 'bg-green-50 text-green-700 hover:bg-green-100'
                  }`}
                >
                  ✓ ОК
                </button>
                <button
                  onClick={() => handleMark(item.id, 'defect')}
                  className={`flex-1 py-2 text-sm rounded-lg font-medium transition-all ${
                    answers[item.id]?.result === 'defect' ? 'bg-red-500 text-white' : 'bg-red-50 text-red-700 hover:bg-red-100'
                  }`}
                >
                  ✕ Не ОК
                </button>
              </div>
            )}
          </div>
        )})}
      </div>

      {/* Нижняя панель (только для инспектора) */}
      {!isReadOnly && activeItem && (
        <div className="bg-white border-t p-4 shrink-0 max-h-[40vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-gray-800 truncate flex-1">{activeItem.question}</h3>
            <button onClick={() => setActiveItemId(null)} className="p-1 hover:bg-gray-100 rounded-lg">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>
          <textarea
            className="input-field mb-3 text-sm" rows={2} placeholder="Комментарий..."
            value={answers[activeItem.id]?.comment ?? ''}
            onChange={(e) => handleComment(activeItem.id, e.target.value)}
          />
          {issuePhotoTargetId ? (
            <div className="space-y-2">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-800">
                Замечание создано. Прикрепите фото нарушения — {issuePhotoCount > 0 ? `загружено: ${issuePhotoCount}` : 'пока без фото'}.
              </div>
              <input
                ref={issuePhotoInputRef} type="file" accept="image/*" className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) uploadIssuePhotoMutation.mutate(file)
                  e.target.value = ''
                }}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => issuePhotoInputRef.current?.click()}
                  disabled={uploadIssuePhotoMutation.isPending}
                  className="btn-outline flex-1 py-2 text-sm"
                >
                  <Camera className="w-4 h-4 inline mr-1" />
                  {issuePhotoCount > 0 ? 'Добавить ещё фото' : 'Сфотографировать'}
                </button>
                <button onClick={finishIssuePhotos} className="btn-primary py-2 px-4 text-sm">
                  Готово
                </button>
              </div>
            </div>
          ) : !showIssueForm ? (
            <button onClick={() => setShowIssueForm(true)} className="btn-outline w-full py-2 text-sm">
              <Plus className="w-4 h-4 inline mr-1" />Создать замечание
            </button>
          ) : (
            <div className="space-y-2">
              <input className="input-field text-sm" placeholder="Заголовок замечания" value={issueTitle} onChange={(e) => setIssueTitle(e.target.value)} />
              <textarea className="input-field text-sm" rows={2} placeholder="Описание (необязательно)" value={issueDesc} onChange={(e) => setIssueDesc(e.target.value)} />
              <div className="flex gap-2">
                <select className="input-field text-sm flex-1" value={issueCriticality} onChange={(e) => setIssueCriticality(e.target.value)}>
                  <option value="low">Низкая</option>
                  <option value="medium">Средняя</option>
                  <option value="high">Высокая</option>
                  <option value="critical">Критическая</option>
                </select>
                <button onClick={() => { if (issueTitle.trim()) createIssueMutation.mutate() }} disabled={!issueTitle.trim()} className="btn-primary py-2 px-4 text-sm">
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
