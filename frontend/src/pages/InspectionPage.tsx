import { useState, useMemo, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { inspectionsApi, checklistsApi, issuesApi, reportsApi, describeUploadError, describeInspectionUpdateError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { InspectionOut, ChecklistTemplateOut, ChecklistItemOut, PhotoOut, IssueOut } from '@/types'
import {
  ArrowLeft, Send, X, AlertTriangle, CheckCircle, Eye,
  CheckCircle2, HelpCircle, ChevronRight, Plus, Camera,
  Flag, RotateCcw, FileText, ClipboardList, ImagePlus
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import PhotoLightbox from '@/components/PhotoLightbox'

type AnswerResult = 'ok' | 'defect' | 'pending'

function DraftPhotoThumb({ file, index, onRemove }: { file: File; index: number; onRemove: () => void }) {
  const [url, setUrl] = useState('')

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file)
    setUrl(nextUrl)
    return () => URL.revokeObjectURL(nextUrl)
  }, [file])

  return (
    <div className="relative rounded-lg border border-blue-200 bg-white p-1 shadow-sm">
      {url && <img src={url} alt={`Фото нарушения ${index + 1}`} className="h-16 w-16 rounded-md object-cover" />}
      <span className="absolute left-1 top-1 rounded bg-black/65 px-1 text-[10px] text-white">Фото {index + 1}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Удалить фото нарушения ${index + 1}`}
        className="absolute -right-2 -top-2 rounded-full bg-red-600 px-1.5 py-0.5 text-xs font-bold text-white shadow"
      >
        ×
      </button>
    </div>
  )
}

// Фото, которое не удалось сохранить даже после автоматических повторов —
// не исчезает тостом (пользователи в поле его не замечали, см. обращение
// про пропавшие "фото ДО"), а остаётся на экране с крупной кнопкой, пока
// человек сам не отправит его ещё раз или не уберёт панель.
function FailedPhotoRetry({ file, onRetry, isRetrying }: { file: File; onRetry: () => void; isRetrying: boolean }) {
  const [url, setUrl] = useState('')

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file)
    setUrl(nextUrl)
    return () => URL.revokeObjectURL(nextUrl)
  }, [file])

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative">
        {url && <img src={url} alt="Фото не сохранилось" className="h-16 w-16 rounded-md object-cover border-2 border-red-400 opacity-70" />}
        <span className="absolute inset-0 flex items-center justify-center">
          <X className="w-7 h-7 text-red-600 drop-shadow" strokeWidth={3.5} />
        </span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={isRetrying}
        className="rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-60 min-h-9"
      >
        {isRetrying ? 'Отправляем…' : 'Отправить ещё раз'}
      </button>
    </div>
  )
}

// Автоматически повторяет отправку фото до 3 раз с паузой между попытками —
// плохая связь в поле обычно "плавает" (пропадает на несколько секунд и
// возвращается), и большинство сбоев так чинятся сами, без единого действия
// от пользователя. Никогда не бросает исключение — либо ok:true, либо после
// исчерпания попыток ok:false с тем же файлом, чтобы вызывающий код мог
// показать file для повторной ручной отправки, а не просто потерять его.
async function uploadPhotoWithRetry(issueId: string, file: File, attempts = 3): Promise<{ ok: boolean; file: File }> {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      await issuesApi.uploadPhoto(issueId, file)
      return { ok: true, file }
    } catch {
      if (attempt < attempts) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 1500))
      }
    }
  }
  return { ok: false, file }
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Запланирован', in_progress: 'В процессе',
  completed: 'Завершён', issues_found: 'Есть нарушения', critical: 'Критический',
}

const ISSUE_CRIT_LABELS: Record<string, string> = {
  low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая',
}
const ISSUE_CRIT_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600', medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-800', critical: 'bg-red-100 text-red-900 font-bold',
}
const ISSUE_STATUS_LABELS: Record<string, string> = {
  open: 'Открыто', assigned: 'Назначено', in_work: 'В работе',
  fixed: 'Исправлено', control: 'На контроле', closed: 'Закрыто',
  overdue: 'Просрочено', revision_needed: 'На доработке',
}
const ISSUE_STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-100 text-red-800', assigned: 'bg-blue-100 text-blue-800', in_work: 'bg-yellow-100 text-yellow-800',
  fixed: 'bg-green-100 text-green-800', control: 'bg-purple-100 text-purple-800',
  closed: 'bg-gray-100 text-gray-600', overdue: 'bg-red-200 text-red-900',
  revision_needed: 'bg-orange-100 text-orange-800',
}

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const inspectionId = id!
  const user = useAuthStore((s) => s.user)

  const [answers, setAnswers] = useState<Record<string, { result: AnswerResult; comment: string }>>({})
  const [activeItemId, setActiveItemId] = useState<string | null>(null)
  const [showIssueForm, setShowIssueForm] = useState(false)
  const [issueTitle, setIssueTitle] = useState('')
  const [issueDesc, setIssueDesc] = useState('')
  const [issueCriticality, setIssueCriticality] = useState('medium')
  const [issueCategoryId, setIssueCategoryId] = useState('')
  const [issueDraftPhotos, setIssueDraftPhotos] = useState<File[]>([])
  // Фото замечания, не сохранившиеся даже после автоповторов — держим
  // сами File, чтобы отправить ещё раз можно было одним тапом, не заставляя
  // человека заново искать снимок в галерее.
  const [failedIssuePhotos, setFailedIssuePhotos] = useState<File[]>([])
  const [photos, setPhotos] = useState<PhotoOut[]>([])
  const [showPhotoPanel, setShowPhotoPanel] = useState(false)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const itemFileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingForItemId, setUploadingForItemId] = useState<string | null>(null)
  // Замечание, для которого сейчас предлагаем прикрепить фото сразу после
  // создания — свои фото, а не общий фотоальбом обхода
  const [issuePhotoTargetId, setIssuePhotoTargetId] = useState<string | null>(null)
  const [issuePhotoCount, setIssuePhotoCount] = useState(0)
  const issuePhotoInputRef = useRef<HTMLInputElement>(null)
  const issueDraftPhotoInputRef = useRef<HTMLInputElement>(null)

  // Reviewer state
  const [reviewerComment, setReviewerComment] = useState('')
  // ?review=1 в ссылке (см. AdminReviewsPage/InspectionReviewList) сразу
  // открывает панель проверки — иначе из списка "Приёмка обходов" было не
  // очевидно, что любой обход (не только "зелёный") можно проверить, для
  // этого нужно было ещё найти и нажать иконку-глаз в шапке.
  const [showReviewPanel, setShowReviewPanel] = useState(searchParams.get('review') === '1')
  const [showCompleteConfirm, setShowCompleteConfirm] = useState(false)

  const { data: inspection, isLoading } = useQuery<InspectionOut>({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  const isInspector = user?.id === inspection?.inspector?.id
  const isAdmin = user?.role === 'admin'
  const isReviewer = user?.role === 'reviewer' || isAdmin
  // Админ не должен ощущать себя "проверяющим" (см. тот же принцип в
  // MapPage.tsx/App.tsx) — те же действия, но подпись роли другая.
  const reviewPanelLabel = isAdmin ? 'администратора' : 'проверяющего'
  // !isInspector, не "isReviewer && !isInspector" — иначе любой ДРУГОЙ
  // инспектор (не владелец обхода и не проверяющий/админ) видел чек-лист
  // полностью редактируемым и мог реально создавать замечания на чужом
  // обходе (открыв URL /inspections/:id с чужим id)
  const isReadOnly = !isInspector

  // Is this inspection returned for revision?
  const isRevision = inspection?.status === 'in_progress' && !!inspection?.reviewer_comment && isInspector
  const usesLegacyChecklist = inspection?.uses_legacy_checklist === true

  const { data: checklists } = useQuery<ChecklistTemplateOut[]>({
    queryKey: ['checklist-template', inspection?.site?.type],
    queryFn: () => checklistsApi.template({ site_type: inspection!.site.type }),
    enabled: usesLegacyChecklist && !!inspection?.site?.type,
  })

  const { data: issueCategories = [] } = useQuery({
    queryKey: ['issue-categories'],
    queryFn: issuesApi.categories,
    staleTime: 5 * 60_000,
  })

  // Замечания, уже созданные по этому обходу — раньше карточка обхода их
  // никак не показывала (только форму создания нового), из-за чего бейдж
  // "N замечаний" в списках был не подтверждаем: открыв сам обход, ни
  // проверяющий, ни инспектор не видели, что это вообще за замечание.
  const { data: existingIssues } = useQuery<IssueOut[]>({
    queryKey: ['issues', inspectionId],
    queryFn: () => issuesApi.list({ inspection_id: inspectionId }).then((r) => r.items),
    enabled: !!inspectionId,
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
      // Пункты чек-листа с "Не ОК" автосоздают замечание на сервере (см.
      // update_inspection) — без этого блок "Замечания по обходу" ниже не
      // узнаёт о нём до перезагрузки страницы.
      queryClient.invalidateQueries({ queryKey: ['issues', inspectionId] })
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
  })

  const reviewMutation = useMutation({
    mutationFn: (data: { status: string; reviewer_comment?: string }) =>
      inspectionsApi.update(inspectionId, data),
    onSuccess: () => {
      toast.success('Проверено')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
      queryClient.invalidateQueries({ queryKey: ['inspections', inspection?.site_id] })
      setShowReviewPanel(false)
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
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
      queryClient.invalidateQueries({ queryKey: ['issues', inspectionId] })
      // Список обходов площадки и личная история — иначе при возврате на
      // SiteDetailPage (staleTime 30с, refetchOnWindowFocus выключен) там
      // ещё какое-то время показывается список без только что завершённого
      // обхода, будто он не сохранился.
      queryClient.invalidateQueries({ queryKey: ['inspections', inspection!.site_id] })
      queryClient.invalidateQueries({ queryKey: ['my-inspections-history'] })
      navigate(`/sites/${inspection!.site_id}`)
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
  })

  const returnMutation = useMutation({
    mutationFn: (data: { status: string; reviewer_comment: string }) =>
      inspectionsApi.update(inspectionId, data),
    onSuccess: () => {
      toast.success('Возвращено на доработку')
      queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
      queryClient.invalidateQueries({ queryKey: ['inspections', inspection?.site_id] })
      setShowReviewPanel(false)
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
  })

  const createIssueMutation = useMutation({
    mutationFn: async () => {
      const issue = await issuesApi.create({
        inspection_id: inspectionId,
        title: issueTitle,
        description: issueDesc || undefined,
        criticality: issueCriticality,
        category_id: issueCategoryId,
      })
      // uploadPhotoWithRetry сама пробует до 3 раз и никогда не бросает
      // исключение — сюда долетают только уже окончательные результаты.
      const results = await Promise.all(
        issueDraftPhotos.map((file) => uploadPhotoWithRetry(issue.id, file))
      )
      return {
        issue,
        uploaded: results.filter((r) => r.ok).length,
        failed: results.filter((r) => !r.ok).map((r) => r.file),
      }
    },
    onSuccess: ({ issue, uploaded, failed }) => {
      setIssuePhotoCount(uploaded)
      setFailedIssuePhotos(failed)
      // Про неудачные фото ничего не говорим тостом — он исчезает сам, и
      // именно так эти фото раньше "терялись" незаметно для инспектора в
      // поле. Вместо этого ниже остаётся постоянная плашка с кнопкой,
      // пока фото не отправится или человек сам не закроет панель.
      toast.success(uploaded > 0 ? `Замечание и фото сохранены (${uploaded})` : 'Замечание создано')
      setIssueTitle('')
      setIssueDesc('')
      setIssueCategoryId('')
      setIssueDraftPhotos([])
      // не закрываем панель сразу — даём прикрепить фото именно к этому
      // замечанию, а не заставляем грузить его отдельно в общий альбом
      setIssuePhotoTargetId(issue.id)
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: () => toast.error('Ошибка создания замечания'),
  })

  const uploadIssuePhotoMutation = useMutation({
    mutationFn: (file: File) => {
      if (!issuePhotoTargetId) return Promise.reject(new Error('no target issue'))
      return uploadPhotoWithRetry(issuePhotoTargetId, file)
    },
    onSuccess: ({ ok, file }) => {
      if (ok) {
        setIssuePhotoCount((c) => c + 1)
        toast.success('Фото замечания загружено')
      } else {
        // Автоповторы исчерпаны — фото остаётся видимым с кнопкой "Отправить
        // ещё раз" ниже, а не пропадает вместе с тостом.
        setFailedIssuePhotos((current) => [...current, file])
      }
    },
    onError: (err) => toast.error(describeUploadError(err)),
  })

  const retryFailedPhotoMutation = useMutation({
    mutationFn: (file: File) => {
      if (!issuePhotoTargetId) return Promise.reject(new Error('no target issue'))
      return uploadPhotoWithRetry(issuePhotoTargetId, file)
    },
    onSuccess: ({ ok, file }) => {
      if (ok) {
        setFailedIssuePhotos((current) => current.filter((f) => f !== file))
        setIssuePhotoCount((c) => c + 1)
        toast.success('Фото сохранено')
      }
      // Если снова не получилось — фото и так уже в failedIssuePhotos,
      // кнопка просто остаётся на месте для следующей попытки.
    },
    onError: () => toast.error('Опять не получилось — проверьте интернет'),
  })

  const finishIssuePhotos = () => {
    setIssuePhotoTargetId(null)
    setIssuePhotoCount(0)
    setFailedIssuePhotos([])
    setShowIssueForm(false)
  }

  // Не даём молча уйти с панели, пока есть не отправленные фото —
  // спрашиваем максимально простыми словами, без технических терминов.
  const handleFinishIssuePhotos = () => {
    if (failedIssuePhotos.length > 0) {
      const leaveAnyway = window.confirm(
        `${failedIssuePhotos.length} ${failedIssuePhotos.length === 1 ? 'фото' : 'фото'} ещё не сохранилось. Закрыть, не дожидаясь отправки?`
      )
      if (!leaveAnyway) return
    }
    finishIssuePhotos()
  }

  const uploadGeneralPhotoMutation = useMutation({
    mutationFn: (file: File) => inspectionsApi.uploadPhoto(inspectionId, file),
    onSuccess: (photo) => {
      setPhotos((prev) => [...prev, photo])
      toast.success('Фото загружено')
    },
    onError: (err) => toast.error(describeUploadError(err)),
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
      // Если ответ ещё не был сохранён, mutationFn выше сохранил его перед
      // загрузкой фото — при результате "Не ОК" это могло создать замечание.
      queryClient.invalidateQueries({ queryKey: ['issues', inspectionId] })
    },
    onError: (err) => {
      setUploadingForItemId(null)
      toast.error(describeUploadError(err))
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
        <button onClick={() => navigate(`/sites/${inspection.site_id}`)} data-prefetch={`/sites/${inspection.site_id}`} className="p-1 -ml-1 hover:bg-primary-700 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-lg truncate">{inspection.site?.courtyard?.name ?? 'Обход'}</h1>
          <div className="flex gap-3 text-xs text-blue-200 mt-0.5">
            {usesLegacyChecklist ? <><span>✓ {stats.ok}</span><span>✕ {stats.nok}</span><span>? {stats.pending}</span></> : <span>Нарушений: {existingIssues?.length ?? 0}</span>}
            {isReadOnly && <span className="opacity-70">| {STATUS_LABELS[inspection.status] ?? inspection.status}</span>}
          </div>
        </div>
        {isInspector && inspection.status === 'in_progress' && (
          <>
            {usesLegacyChecklist && <button onClick={() => saveMutation.mutate()} className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30">
              Сохранить
            </button>}
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
            showPhotoPanel ? 'bg-white/30' : 'bg-white/20 hover:bg-white/30'
          }`}
          aria-label="Открыть фотографии обхода"
        >
          <Camera className="w-4 h-4 inline mr-1" />
          <span className="hidden sm:inline">Фото</span>{photos.length > 0 ? ` (${photos.length})` : isInspector ? ' — нужны' : ''}
        </button>
        <button
          onClick={() => reportsApi.openPdfReport(inspectionId).catch(() => toast.error('Не удалось открыть отчёт'))}
          className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30"
          title="PDF-отчёт"
        >
          <FileText className="w-4 h-4 inline mr-1" />
        </button>
        <button
          onClick={() => navigate(`/inspections/${inspectionId}/summary`)}
          data-prefetch={`/inspections/${inspectionId}/summary`}
          className="text-xs bg-white/20 px-3 py-1.5 rounded-lg hover:bg-white/30"
          title="Сводка обхода"
        >
          <ClipboardList className="w-4 h-4 inline mr-1" />
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

      {isInspector && (
        <div className="bg-blue-50 border-b border-blue-200 px-4 py-3 shrink-0">
          <div className="flex items-start gap-3 max-w-3xl mx-auto">
            <HelpCircle className="w-5 h-5 text-blue-700 shrink-0 mt-0.5" />
            <div className="text-sm text-blue-950">
              <div className="font-bold">Как добавить фото</div>
              <div className="mt-1 leading-5 text-blue-800">
                1. Отметьте результат пункта. 2. Нажмите большую кнопку «Добавить фото». 3. Проверьте, что снимок появился под нужным пунктом.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Замечания по этому обходу */}
      {existingIssues && existingIssues.length > 0 && (
        <div className="bg-white border-b p-3 shrink-0 space-y-2">
          <div className="text-xs font-semibold text-gray-500 uppercase">
            Замечания по обходу ({existingIssues.length})
          </div>
          {existingIssues.map((issue) => {
            const detailPath = isAdmin ? `/admin/issues/${issue.id}` : `/issues/${issue.id}`
            const canOpen = isReviewer
            return (
              <div
                key={issue.id}
                role={canOpen ? 'button' : undefined}
                tabIndex={canOpen ? 0 : undefined}
                onClick={canOpen ? () => navigate(detailPath) : undefined}
                className={`rounded-lg border border-gray-200 p-2.5 ${canOpen ? 'cursor-pointer hover:border-primary-300' : ''}`}
              >
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={`badge text-[10px] ${ISSUE_CRIT_COLORS[issue.criticality] ?? 'bg-gray-100'}`}>
                    {ISSUE_CRIT_LABELS[issue.criticality] ?? issue.criticality}
                  </span>
                  <span className={`badge text-[10px] ${ISSUE_STATUS_COLORS[issue.status] ?? 'bg-gray-100'}`}>
                    {ISSUE_STATUS_LABELS[issue.status] ?? issue.status}
                  </span>
                </div>
                <div className="text-sm font-medium text-gray-800">{issue.title}</div>
                {issue.description && (
                  <div className="text-xs text-gray-500 mt-0.5">{issue.description}</div>
                )}
                {(issue.photos?.length ?? 0) > 0 && (
                  <div className="flex gap-1.5 mt-1.5">
                    {issue.photos!.map((p) => (
                      <button key={p.id} onClick={(e) => { e.stopPropagation(); setLightboxUrl(p.url) }}>
                        <img src={p.thumbnail_url ?? p.url} alt="" className="w-10 h-10 object-cover rounded border" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Complete confirmation */}
      {showCompleteConfirm && isInspector && (
        <div className="bg-white border-b p-3 shrink-0 space-y-3">
          <div className="text-sm font-semibold text-gray-800">Завершить обход</div>
          <p className="text-xs text-gray-500">
            {usesLegacyChecklist
              ? <>Проверено ✓{stats.ok} пунктов, выявлено ✕{stats.nok} нарушений.{stats.pending > 0 && ` Осталось ${stats.pending} непроверенных.`}</>
              : <>Создано нарушений: {existingIssues?.length ?? 0}. Итоговый статус определит сервер.</>}
          </p>
          {usesLegacyChecklist && missingRequiredPhotoItems.length > 0 && (
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
              disabled={completeMutation.isPending || (usesLegacyChecklist && missingRequiredPhotoItems.length > 0)}
              className="flex-1 py-2 text-sm bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-40"
            >
              {usesLegacyChecklist ? '✓ Всё в порядке' : 'Завершить обход'}
            </button>
            {usesLegacyChecklist && stats.nok > 0 && (
              <button
                onClick={() => completeMutation.mutate('issues_found')}
                disabled={completeMutation.isPending || missingRequiredPhotoItems.length > 0}
                className="flex-1 py-2 text-sm bg-orange-600 text-white rounded-lg font-medium hover:bg-orange-700 disabled:opacity-40"
              >
                ⚠ Завершить с нарушениями
              </button>
            )}
          </div>
        </div>
      )}

      {/* Панель проверяющего — не для своего же обхода (самопроверка), см. кнопку-тоггл выше */}
      {showReviewPanel && isReviewer && !isInspector && (
        <div className="bg-white border-b p-3 shrink-0 space-y-3">
          <div className="text-sm font-semibold text-gray-800">Проверка обхода</div>
          <textarea
            className="input-field text-sm"
            rows={2}
            placeholder={`Комментарий ${reviewPanelLabel}...`}
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
        <div className="bg-white border-b p-4 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <div className="text-base font-bold text-gray-800">
                  {isReadOnly ? 'Фото обхода' : 'Общее фото площадки'}
                </div>
                <div className="text-sm text-gray-500 mt-0.5">
                  {isReadOnly ? 'Нажмите на снимок, чтобы увеличить.' : 'Снимите площадку целиком, чтобы было понятно, где проходил обход.'}
                </div>
              </div>
              <span className="badge bg-blue-100 text-blue-800 shrink-0">
                {generalPhotos.length === 0 ? '0 фото' : `${generalPhotos.length} ${generalPhotos.length === 1 ? 'фото' : 'фото'}`}
              </span>
            </div>
            <div className="flex flex-wrap gap-3 mb-3">
              {generalPhotos.map((p, index) => (
                <button key={p.id} onClick={() => setLightboxUrl(p.url)} className="group text-left" aria-label={`Открыть общее фото ${index + 1}`}>
                  <img src={p.url} alt={`Общее фото ${index + 1}`} className="w-24 h-24 object-cover rounded-xl border-2 border-blue-200 group-hover:border-blue-500" />
                  <span className="block text-xs text-gray-500 mt-1 text-center">Фото {index + 1}</span>
                </button>
              ))}
              {generalPhotos.length === 0 && (
                <div className="w-full rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500 flex items-center gap-3">
                  <Camera className="w-6 h-6 text-gray-400 shrink-0" />
                  <span>Здесь появится снимок общего вида площадки</span>
                </div>
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
              <button onClick={() => fileInputRef.current?.click()} disabled={uploadGeneralPhotoMutation.isPending} className="w-full sm:w-auto btn-primary py-3 px-5 text-base flex items-center justify-center gap-2">
                <ImagePlus className="w-5 h-5" />
                {uploadGeneralPhotoMutation.isPending ? 'Загружаем фото…' : 'Добавить фото общего вида'}
              </button>
            </>
          )}
          </div>
        </div>
      )}

      {/* Скрытый input для загрузки фото пункта */}
      {!isReadOnly && (
        <input ref={itemFileInputRef} type="file" accept="image/*" className="hidden" onChange={handleItemPhotoUpload} />
      )}

      {/* Прогресс-бар */}
      {usesLegacyChecklist && <div className="h-1 bg-gray-200 shrink-0">
        <div
          className="h-full bg-green-500 transition-all duration-300"
          style={{ width: `${stats.total > 0 ? ((stats.ok + stats.nok) / stats.total) * 100 : 0}%` }}
        />
      </div>}

      <div className="overflow-y-auto flex-1 p-4 space-y-3">
        {usesLegacyChecklist && allItems.map((item) => {
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
                  <div className="mt-3 rounded-xl bg-gray-50 p-2.5">
                    <div className="text-xs font-semibold text-gray-600 mb-2">Фото этого пункта</div>
                    <div className="flex flex-wrap gap-3">
                    {itemPhotos.map((p, photoIndex) => (
                      <button key={p.id} onClick={(e) => { e.stopPropagation(); setLightboxUrl(p.url) }} className="text-left" aria-label={`Открыть фото пункта ${photoIndex + 1}`}>
                        <img src={p.url} alt={`Фото пункта ${photoIndex + 1}`} className="w-20 h-20 object-cover rounded-xl border-2 border-gray-200" />
                        <span className="block text-[11px] text-gray-500 mt-1 text-center">Фото {photoIndex + 1}</span>
                      </button>
                    ))}
                    </div>
                  </div>
                )}

                {!isReadOnly && answers[item.id]?.result === 'defect' && (
                  <div className="mt-2">
                    <button
                      onClick={() => triggerItemUpload(item.id)}
                      disabled={uploadItemPhotoMutation.isPending && uploadingForItemId === item.id}
                      className="w-full py-3 rounded-xl font-bold text-base bg-red-50 text-red-700 border-2 border-red-200 hover:bg-red-100 flex items-center justify-center gap-2 disabled:opacity-60"
                    >
                      <ImagePlus className="w-5 h-5" />
                      {uploadItemPhotoMutation.isPending && uploadingForItemId === item.id ? 'Загружаем фото…' : 'Добавить фото нарушения'}
                    </button>
                  </div>
                )}
                {/* requires_photo обязателен независимо от результата — этот
                    пункт нужен отдельно от кнопки выше, потому что «Фото
                    общего вида площадки» (единственный requires_photo пункт
                    в шаблонах) естественно отмечается «ОК», а не «Не ОК», и
                    без этой кнопки прикрепить обязательное фото было вообще
                    негде — обход блокировался на завершении без возможности
                    выполнить требование. */}
                {!isReadOnly && item.requires_photo && answers[item.id]?.result === 'ok' && (
                  <div className="mt-2">
                    <button
                      onClick={() => triggerItemUpload(item.id)}
                      disabled={uploadItemPhotoMutation.isPending && uploadingForItemId === item.id}
                      className="w-full py-3 rounded-xl font-bold text-base bg-blue-50 text-blue-700 border-2 border-blue-200 hover:bg-blue-100 flex items-center justify-center gap-2 disabled:opacity-60"
                    >
                      <ImagePlus className="w-5 h-5" />
                      {uploadItemPhotoMutation.isPending && uploadingForItemId === item.id ? 'Загружаем фото…' : 'Добавить обязательное фото'}
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
      {!isReadOnly && (usesLegacyChecklist ? activeItem : true) && (
        <div className="bg-white border-t p-4 shrink-0 max-h-[40vh] overflow-y-auto">
          {activeItem && <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-gray-800 truncate flex-1">{activeItem.question}</h3>
            <button onClick={() => setActiveItemId(null)} className="p-1 hover:bg-gray-100 rounded-lg">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>}
          {activeItem && <textarea
            className="input-field mb-3 text-sm" rows={2} placeholder="Комментарий..."
            value={answers[activeItem.id]?.comment ?? ''}
            onChange={(e) => handleComment(activeItem.id, e.target.value)}
          />}
          {issuePhotoTargetId ? (
            <div className="space-y-2">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-800">
                Замечание создано. Прикрепите фото нарушения — {issuePhotoCount > 0 ? `загружено: ${issuePhotoCount}` : 'пока без фото'}.
              </div>
              {failedIssuePhotos.length > 0 && (
                <div className="bg-red-50 border-2 border-red-300 rounded-xl p-3 space-y-2">
                  <div className="text-sm font-bold text-red-800">
                    {failedIssuePhotos.length === 1 ? 'Одно фото не сохранилось' : `${failedIssuePhotos.length} фото не сохранились`}
                  </div>
                  <div className="text-xs text-red-700">Бывает из-за плохой связи. Нажмите на кнопку под фото, чтобы отправить его ещё раз.</div>
                  <div className="flex flex-wrap gap-3">
                    {failedIssuePhotos.map((file, idx) => (
                      <FailedPhotoRetry
                        key={`${file.name}-${file.lastModified}-${idx}`}
                        file={file}
                        onRetry={() => retryFailedPhotoMutation.mutate(file)}
                        isRetrying={retryFailedPhotoMutation.isPending && retryFailedPhotoMutation.variables === file}
                      />
                    ))}
                  </div>
                </div>
              )}
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
                  {uploadIssuePhotoMutation.isPending ? 'Загружаем фото…' : issuePhotoCount > 0 ? 'Добавить ещё фото' : 'Сфотографировать'}
                </button>
                <button onClick={handleFinishIssuePhotos} className="btn-primary py-2 px-4 text-sm">
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
              <select aria-label="Категория" className="input-field text-sm" value={issueCategoryId} onChange={(e) => setIssueCategoryId(e.target.value)}>
                <option value="">Выберите категорию</option>
                {issueCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select>
              <input
                ref={issueDraftPhotoInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  const selected = Array.from(e.target.files ?? [])
                  setIssueDraftPhotos((current) => [...current, ...selected].slice(0, 5))
                  e.target.value = ''
                }}
              />
              <div className="rounded-xl border-2 border-dashed border-blue-200 bg-blue-50 p-3">
                <div className="flex items-start gap-2">
                  <ImagePlus className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
                  <div>
                    <p className="font-semibold text-sm text-blue-900">Фото нарушения</p>
                    <p className="mt-0.5 text-xs text-blue-700">Выберите снимок — он прикрепится именно к этому замечанию.</p>
                    <p className="mt-1 text-[11px] text-blue-600">Допустимые форматы: JPG, JPEG, PNG, WEBP, HEIC, HEIF, GIF.</p>
                  </div>
                </div>
                {issueDraftPhotos.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {issueDraftPhotos.map((file, index) => (
                      <DraftPhotoThumb
                        key={`${file.name}-${file.lastModified}-${index}`}
                        file={file}
                        index={index}
                        onRemove={() => setIssueDraftPhotos((current) => current.filter((_, i) => i !== index))}
                      />
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => issueDraftPhotoInputRef.current?.click()}
                  disabled={issueDraftPhotos.length >= 5}
                  className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                >
                  <Camera className="h-4 w-4" />
                  {issueDraftPhotos.length >= 5 ? 'Добавлено максимум 5 фото' : issueDraftPhotos.length ? 'Добавить ещё фото' : 'Добавить фото нарушения'}
                </button>
              </div>
              <div className="flex gap-2">
                <select className="input-field text-sm flex-1" value={issueCriticality} onChange={(e) => setIssueCriticality(e.target.value)}>
                  <option value="low">Низкая</option>
                  <option value="medium">Средняя</option>
                  <option value="high">Высокая</option>
                  <option value="critical">Критическая</option>
                </select>
                <button onClick={() => { if (issueTitle.trim() && issueCategoryId) createIssueMutation.mutate() }} disabled={!issueTitle.trim() || !issueCategoryId || createIssueMutation.isPending} className="btn-primary py-2 px-4 text-sm">
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      <PhotoLightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
    </div>
  )
}
