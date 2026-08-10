import { useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { issuesApi, inspectionsApi } from '@/lib/api'
import { usePhotoUpload } from '@/lib/usePhotoUpload'
import { useAuthStore } from '@/stores/auth'
import type { IssueOut } from '@/types'
import {
  Camera, CheckCircle2, AlertTriangle, XCircle,
  Calendar, User, MapPin, Clock, RotateCcw, GitCompare,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'
import BeforeAfterSlider from '@/components/BeforeAfterSlider'
import { guardDemoAction } from '@/stores/demoMode'

const STATUS_LABELS: Record<string, string> = {
  open: 'Открыто', assigned: 'Назначено', in_work: 'В работе',
  fixed: 'Исправлено', control: 'На контроле', closed: 'Закрыто',
  overdue: 'Просрочено', revision_needed: 'На доработке',
}
const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-100 text-red-800', assigned: 'bg-blue-100 text-blue-800', in_work: 'bg-yellow-100 text-yellow-800',
  fixed: 'bg-green-100 text-green-800', control: 'bg-purple-100 text-purple-800',
  closed: 'bg-gray-100 text-gray-600', overdue: 'bg-red-200 text-red-900',
  revision_needed: 'bg-orange-100 text-orange-800',
}
const CRIT_LABELS: Record<string, string> = { low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая' }
const CRIT_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600', medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-800', critical: 'bg-red-100 text-red-900 font-bold',
}

export default function IssueFixPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const issueId = id!
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [fixComment, setFixComment] = useState('')
  const [reviewerComment, setReviewerComment] = useState('')

  const isAdmin = user?.role === 'admin'
  const isReviewerLike = user?.role === 'reviewer' || isAdmin
  // Смонтирована на /issues/:id (reviewer) и /admin/issues/:id (admin) —
  // см. тот же паттерн в IssuesPage.tsx.
  const issuesListPath = isAdmin ? '/admin/issues' : '/issues'

  const { data: issue, isLoading } = useQuery<IssueOut>({
    queryKey: ['issue', issueId], queryFn: () => issuesApi.get(issueId), enabled: !!issueId,
  })

  const fixPhotoUpload = useMutation({
    mutationFn: (file: File) => issuesApi.uploadFixPhoto(issueId, file),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['issue', issueId] }); toast.success('Фото исправления загружено') },
    onError: () => toast.error('Ошибка загрузки фото'),
  })

  const { isUploading, handleFileInput } = usePhotoUpload((file) => fixPhotoUpload.mutateAsync(file))

  const markFixedMutation = useMutation({
    mutationFn: () => issuesApi.update(issueId, { status: 'fixed', fix_comment: fixComment || undefined }),
    onSuccess: () => {
      toast.success('Исправление зафиксировано!')
      queryClient.invalidateQueries({ queryKey: ['issue', issueId] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      navigate(issuesListPath)
    },
    onError: () => toast.error('Ошибка сохранения'),
  })

  const acceptMutation = useMutation({
    mutationFn: () => issuesApi.update(issueId, { status: 'closed', reviewer_comment: reviewerComment || undefined }),
    onSuccess: () => {
      toast.success('Исправление принято!')
      queryClient.invalidateQueries({ queryKey: ['issue', issueId] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Ошибка')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => issuesApi.update(issueId, { status: 'revision_needed', reviewer_comment: reviewerComment }),
    onSuccess: () => {
      toast.success('Отправлено на доработку')
      queryClient.invalidateQueries({ queryKey: ['issue', issueId] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Ошибка')
    },
  })

  if (isLoading) return <div className="h-full flex items-center justify-center bg-gray-50"><div className="text-gray-400">Загрузка...</div></div>
  if (!issue) return <div className="h-full flex items-center justify-center bg-gray-50"><div className="text-gray-400">Замечание не найдено</div></div>

  const fixPhotos = issue.fix_photos ?? []

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(issuesListPath)} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-lg truncate">Исправление нарушения</h1>
            <p className="text-blue-200 text-xs">Замечание #{issueId.slice(0, 8)}</p>
          </div>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 p-4 space-y-4">
        {/* Основная информация */}
        <div className="card space-y-3">
          <h2 className="font-semibold text-gray-800">{issue.title}</h2>
          {issue.description && <p className="text-sm text-gray-600">{issue.description}</p>}
          <div className="flex flex-wrap gap-2">
            <span className={`badge text-xs ${CRIT_COLORS[issue.criticality] ?? 'bg-gray-100'}`}>{CRIT_LABELS[issue.criticality] ?? issue.criticality}</span>
            <span className={`badge text-xs ${STATUS_COLORS[issue.status] ?? 'bg-gray-100'}`}>{STATUS_LABELS[issue.status] ?? issue.status}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
            {issue.site_name && <div className="flex items-center gap-1"><MapPin className="w-3 h-3" />{issue.site_name}</div>}
            {issue.district_name && <div className="flex items-center gap-1"><MapPin className="w-3 h-3" />{issue.district_name}</div>}
            {issue.creator && <div className="flex items-center gap-1"><User className="w-3 h-3" />Создал: {issue.creator.full_name}</div>}
            {issue.assigned_user && <div className="flex items-center gap-1"><User className="w-3 h-3" />{issue.assigned_user.full_name}</div>}
            {issue.due_date && <div className="flex items-center gap-1"><Calendar className="w-3 h-3" />До {new Date(issue.due_date).toLocaleDateString('ru')}</div>}
            <div className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(issue.created_at).toLocaleDateString('ru')}</div>
          </div>
          <button onClick={() => navigate(`/inspections/${issue.inspection_id}`)} className="text-xs text-primary-600 hover:text-primary-800 underline">Открыть обход</button>
        </div>

        {/* До Do youрусский комментарий (если вернули на доработку) */}
        {issue.reviewer_comment && issue.status === 'revision_needed' && (
          <div className="card bg-orange-50 border-orange-200">
            <h3 className="font-semibold text-orange-800 mb-2 flex items-center gap-1.5"><RotateCcw className="w-4 h-4" />Возвращено на доработку</h3>
            <p className="text-sm text-orange-700 whitespace-pre-wrap">{issue.reviewer_comment}</p>
          </div>
        )}

        {/* Слайдер ДО/ПОСЛЕ + загрузка фото */}
        <IssuePhotoComparison inspectionId={issue.inspection_id} issuePhotos={issue.photos ?? []} fixPhotos={fixPhotos} />

        {issue.status !== 'closed' && (
          <div className="card space-y-2">
            <h3 className="text-sm font-medium text-gray-600 flex items-center gap-1"><Camera className="w-4 h-4" />Загрузить фото исправления</h3>
            <div className="flex gap-2">
              {/* Без capture="environment" — см. комментарий в InspectionPage.tsx:
                  на некоторых Android WebView с заблокированным разрешением
                  камеры input с этим атрибутом молча ничего не делал по тапу */}
              <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileInput} />
              <button onClick={() => fileInputRef.current?.click()} disabled={isUploading} className="btn-outline flex items-center gap-1.5 py-2 px-4 text-sm">
                {isUploading ? (
                  <><span className="w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />Загрузка...</>
                ) : (
                  <><Camera className="w-4 h-4" />Загрузить фото</>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Блок «Зафиксировать исправление» — доступен и после revision_needed,
            чтобы проверяющий мог довести замечание обратно до fixed после
            того как админ вернул его на доработку (иначе замечание зависало
            без единой кнопки, ведущей к повторной отправке) */}
        {isReviewerLike && issue.status !== 'fixed' && issue.status !== 'closed' && (
          <div className="card space-y-3">
            <h3 className="font-semibold text-gray-800">Зафиксировать исправление</h3>
            <textarea className="input-field text-sm" rows={3} placeholder="Опишите, что было сделано для устранения нарушения..." value={fixComment} onChange={(e) => setFixComment(e.target.value)} />
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div><div className="font-medium mb-0.5">Перед фиксацией проверьте:</div><ul className="list-disc list-inside space-y-0.5"><li>Фото исправления загружены</li><li>Нарушение действительно устранено</li><li>Описание исправления заполнено</li></ul></div>
            </div>
            <button onClick={() => guardDemoAction(() => markFixedMutation.mutate())} disabled={markFixedMutation.isPending || fixPhotos.length === 0} className="btn-primary w-full py-3 flex items-center justify-center gap-2 disabled:opacity-50">
              {markFixedMutation.isPending ? <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <CheckCircle2 className="w-5 h-5" />}
              Зафиксировать исправление
            </button>
            {fixPhotos.length === 0 && <p className="text-xs text-gray-400 text-center">Загрузите хотя бы одно фото исправления</p>}
          </div>
        )}

        {/* Приёмка админом */}
        {isAdmin && issue.status === 'fixed' && (
          <div className="card space-y-3 bg-white border-2 border-primary-200">
            <h3 className="font-semibold text-gray-800 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-primary-600" />Приёмка исправления</h3>
            {issue.fix_comment && <div className="bg-green-50 rounded-lg p-3 text-sm text-green-800"><div className="font-medium text-xs text-green-600 mb-0.5">Описание от проверяющего:</div>{issue.fix_comment}</div>}
            <textarea className="input-field text-sm" rows={2} placeholder="Комментарий (необязательно при приёмке, обязательно при возврате)..." value={reviewerComment} onChange={(e) => setReviewerComment(e.target.value)} />
            <div className="flex gap-2">
              <button onClick={() => guardDemoAction(() => acceptMutation.mutate())} disabled={acceptMutation.isPending} className="btn-primary flex-1 py-3 flex items-center justify-center gap-2">
                {acceptMutation.isPending ? <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <CheckCircle2 className="w-5 h-5" />}Принять
              </button>
              <button
                onClick={() => guardDemoAction(() => rejectMutation.mutate())}
                disabled={rejectMutation.isPending || !reviewerComment.trim()}
                title={!reviewerComment.trim() ? 'Укажите, что нужно доработать' : undefined}
                className="btn-danger flex-1 py-3 flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {rejectMutation.isPending ? <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <XCircle className="w-5 h-5" />}На доработку
              </button>
            </div>
            {!reviewerComment.trim() && <p className="text-xs text-gray-400 text-center">Для возврата на доработку нужен комментарий — что исправить</p>}
          </div>
        )}

        {/* Уже исправлено — для не-админов */}
        {!isAdmin && issue.fix_comment && (issue.status === 'fixed' || issue.status === 'closed') && (
          <div className="card bg-green-50 border-green-200">
            <h3 className="font-semibold text-green-800 mb-2 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" />{issue.status === 'closed' ? 'Принято' : 'Исправление зафиксировано'}</h3>
            <p className="text-sm text-green-700">{issue.fix_comment}</p>
          </div>
        )}
      </div>
    </div>
  )
}

/** Сравнение фото ДО/ПОСЛЕ через слайдер */
function IssuePhotoComparison({
  inspectionId, issuePhotos, fixPhotos,
}: { inspectionId: string; issuePhotos: { id: string; url: string }[]; fixPhotos: { id: string; url: string }[] }) {
  const [pairIndex, setPairIndex] = useState(0)
  const { data: inspection } = useQuery({ queryKey: ['inspection', inspectionId], queryFn: () => inspectionsApi.get(inspectionId), enabled: !!inspectionId })
  // Фото самого замечания — если инспектор их прикрепил при создании
  // (см. InspectionPage.tsx); для старых замечаний без своих фото падаем
  // назад на общий альбом обхода, как было раньше
  const beforePhotos = issuePhotos.length > 0
    ? issuePhotos
    : inspection?.photos?.filter((p) => p.target_type === 'inspection') ?? []
  const totalPairs = Math.max(beforePhotos.length, fixPhotos.length, 1)
  const safeIndex = Math.min(pairIndex, totalPairs - 1)
  const beforeUrl = beforePhotos[safeIndex]?.url
  const afterUrl = fixPhotos[safeIndex]?.url
  if (!inspection) return null

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800 flex items-center gap-1.5"><GitCompare className="w-4 h-4 text-primary-600" />Сравнение ДО / ПОСЛЕ</h3>
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-medium">ДО: {beforePhotos.length}</span>
          <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full font-medium">ПОСЛЕ: {fixPhotos.length}</span>
        </div>
      </div>
      <BeforeAfterSlider beforeUrl={beforeUrl} afterUrl={afterUrl} />
      {totalPairs > 1 && (
        <>
          <div className="flex items-center justify-center gap-2">
            <button onClick={() => setPairIndex((v) => Math.max(0, v - 1))} disabled={safeIndex === 0} className="p-1 rounded hover:bg-gray-200 disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
            <span className="text-xs text-gray-500 font-medium tabular-nums">{safeIndex + 1} / {totalPairs}</span>
            <button onClick={() => setPairIndex((v) => Math.min(totalPairs - 1, v + 1))} disabled={safeIndex >= totalPairs - 1} className="p-1 rounded hover:bg-gray-200 disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
          </div>
          <div className="flex gap-1.5 justify-center flex-wrap">
            {Array.from({ length: totalPairs }).map((_, i) => (
              <button key={i} onClick={() => setPairIndex(i)} className={`w-8 h-8 rounded-lg border-2 overflow-hidden transition-all ${i === safeIndex ? 'border-primary-500 scale-110 shadow-md' : 'border-gray-200 opacity-60 hover:opacity-100'}`}>
                {(beforePhotos[i]?.url || fixPhotos[i]?.url) ? <img src={beforePhotos[i]?.url || fixPhotos[i]?.url} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full bg-gray-200 flex items-center justify-center text-gray-400 text-[8px]">{i + 1}</div>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
