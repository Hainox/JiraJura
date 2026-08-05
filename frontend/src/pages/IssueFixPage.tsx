import { useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { issuesApi, inspectionsApi } from '@/lib/api'
import { usePhotoUpload } from '@/lib/usePhotoUpload'
import type { IssueOut } from '@/types'
import {
  Camera, ImagePlus, CheckCircle2, AlertTriangle,
  Calendar, User, MapPin, Clock,
} from 'lucide-react'
import { notify as toast } from '@/lib/toast'

const STATUS_LABELS: Record<string, string> = {
  open: 'Открыто', assigned: 'Назначено', in_work: 'В работе',
  fixed: 'Исправлено', control: 'На контроле', closed: 'Закрыто', overdue: 'Просрочено',
}
const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-100 text-red-800',
  assigned: 'bg-blue-100 text-blue-800',
  in_work: 'bg-yellow-100 text-yellow-800',
  fixed: 'bg-green-100 text-green-800',
  control: 'bg-purple-100 text-purple-800',
  closed: 'bg-gray-100 text-gray-600',
  overdue: 'bg-red-200 text-red-900',
}
const CRIT_LABELS: Record<string, string> = {
  low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая',
}
const CRIT_COLORS: Record<string, string> = {
  low: 'bg-gray-100 text-gray-600',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-900 font-bold',
}

export default function IssueFixPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const issueId = id!
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [fixComment, setFixComment] = useState('')

  const { data: issue, isLoading } = useQuery<IssueOut>({
    queryKey: ['issue', issueId],
    queryFn: () => issuesApi.get(issueId),
    enabled: !!issueId,
  })

  const fixPhotoUpload = useMutation({
    mutationFn: (file: File) => issuesApi.uploadFixPhoto(issueId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueId] })
      toast.success('Фото исправления загружено')
    },
    onError: () => toast.error('Ошибка загрузки фото'),
  })

  const { isUploading, handleFileInput } = usePhotoUpload((file) => fixPhotoUpload.mutateAsync(file))

  const markFixedMutation = useMutation({
    mutationFn: () =>
      issuesApi.update(issueId, {
        status: 'fixed',
        fix_comment: fixComment || undefined,
      }),
    onSuccess: () => {
      toast.success('Исправление зафиксировано!')
      queryClient.invalidateQueries({ queryKey: ['issue', issueId] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      navigate('/issues')
    },
    onError: () => toast.error('Ошибка сохранения'),
  })

  const handleMarkFixed = () => markFixedMutation.mutate()

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Загрузка...</div>
      </div>
    )
  }

  if (!issue) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Замечание не найдено</div>
      </div>
    )
  }

  const fixPhotos = issue.fix_photos ?? []

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-primary-800 text-white px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/issues')} className="p-1.5 rounded-lg hover:bg-primary-700 transition-colors shrink-0">
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

          {issue.description && (
            <p className="text-sm text-gray-600">{issue.description}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <span className={`badge text-xs ${CRIT_COLORS[issue.criticality] ?? 'bg-gray-100'}`}>
              {CRIT_LABELS[issue.criticality] ?? issue.criticality}
            </span>
            <span className={`badge text-xs ${STATUS_COLORS[issue.status] ?? 'bg-gray-100'}`}>
              {STATUS_LABELS[issue.status] ?? issue.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
            {issue.site_name && (
              <div className="flex items-center gap-1">
                <MapPin className="w-3 h-3" />
                {issue.site_name}
              </div>
            )}
            {issue.district_name && (
              <div className="flex items-center gap-1">
                <MapPin className="w-3 h-3" />
                {issue.district_name}
              </div>
            )}
            {issue.creator && (
              <div className="flex items-center gap-1">
                <User className="w-3 h-3" />
                Создал: {issue.creator.full_name}
              </div>
            )}
            {issue.assigned_user && (
              <div className="flex items-center gap-1">
                <User className="w-3 h-3" />
                {issue.assigned_user.full_name}
              </div>
            )}
            {issue.due_date && (
              <div className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                До {new Date(issue.due_date).toLocaleDateString('ru')}
              </div>
            )}
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(issue.created_at).toLocaleDateString('ru')}
            </div>
          </div>

          {/* Ссылка на обход */}
          <button
            onClick={() => navigate(`/inspections/${issue.inspection_id}`)}
            className="text-xs text-primary-600 hover:text-primary-800 underline"
          >
            Открыть обход
          </button>
        </div>

        {/* Фото ДО — из обхода (смотрим через API inspections) */}
        <IssueBeforePhotos inspectionId={issue.inspection_id} />

        {/* Фото ПОСЛЕ — исправления */}
        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-green-600" />
            Фото исправления ({fixPhotos.length})
          </h3>

          {fixPhotos.length > 0 ? (
            <div className="flex flex-wrap gap-2 mb-3">
              {fixPhotos.map((p) => (
                <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                  <img
                    src={p.url}
                    alt="Фото исправления"
                    className="w-24 h-24 object-cover rounded-lg border-2 border-green-200 hover:border-green-400 transition-colors"
                  />
                </a>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-400 italic bg-gray-50 rounded-lg p-3 mb-3">
              <AlertTriangle className="w-4 h-4 inline mr-1 text-amber-400" />
              Фото исправлений ещё не загружены
            </div>
          )}

          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={handleFileInput}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="btn-outline flex items-center gap-1.5 py-2 px-4 text-sm"
            >
              {isUploading ? (
                <>
                  <span className="w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
                  Загрузка...
                </>
              ) : (
                <>
                  <Camera className="w-4 h-4" />
                  Загрузить фото исправления
                </>
              )}
            </button>
          </div>
        </div>

        {/* Комментарий к исправлению + кнопка фиксации */}
        {issue.status !== 'closed' && issue.status !== 'fixed' && (
          <div className="card space-y-3">
            <h3 className="font-semibold text-gray-800">Зафиксировать исправление</h3>

            <textarea
              className="input-field text-sm"
              rows={3}
              placeholder="Опишите, что было сделано для устранения нарушения..."
              value={fixComment}
              onChange={(e) => setFixComment(e.target.value)}
            />

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium mb-0.5">Перед фиксацией проверьте:</div>
                <ul className="list-disc list-inside space-y-0.5">
                  <li>Фото исправления загружены и отображаются</li>
                  <li>Нарушение действительно устранено</li>
                  <li>Описание исправления заполнено</li>
                </ul>
              </div>
            </div>

            <button
              onClick={handleMarkFixed}
              disabled={markFixedMutation.isPending || fixPhotos.length === 0}
              className="btn-primary w-full py-3 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {markFixedMutation.isPending ? (
                <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <CheckCircle2 className="w-5 h-5" />
              )}
              Зафиксировать исправление
            </button>

            {fixPhotos.length === 0 && (
              <p className="text-xs text-gray-400 text-center">
                Загрузите хотя бы одно фото исправления
              </p>
            )}
          </div>
        )}

        {/* Уже зафиксировано */}
        {issue.fix_comment && (issue.status === 'fixed' || issue.status === 'closed') && (
          <div className="card bg-green-50 border-green-200">
            <h3 className="font-semibold text-green-800 mb-2 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" />
              Исправление зафиксировано
            </h3>
            <p className="text-sm text-green-700">{issue.fix_comment}</p>
            {fixPhotos.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-green-600 mb-1 font-medium">Фото исправления:</div>
                <div className="flex flex-wrap gap-2">
                  {fixPhotos.map((p) => (
                    <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                      <img src={p.url} alt="" className="w-20 h-20 object-cover rounded-lg border-2 border-green-200" />
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** Просмотр фото обхода (ДО) */
function IssueBeforePhotos({ inspectionId }: { inspectionId: string }) {
  const { data: inspection } = useQuery({
    queryKey: ['inspection', inspectionId],
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: !!inspectionId,
  })

  const photos = inspection?.photos?.filter((p) => p.target_type === 'inspection') ?? []

  if (!inspection) return null

  return (
    <div className="card">
      <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-1.5">
        <ImagePlus className="w-4 h-4 text-blue-600" />
        Фото обхода — ДО исправления ({photos.length})
      </h3>

      {photos.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {photos.map((p) => (
            <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
              <img
                src={p.url}
                alt="Фото до исправления"
                className="w-24 h-24 object-cover rounded-lg border hover:border-blue-400 transition-colors"
              />
            </a>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-400 italic bg-gray-50 rounded-lg p-3">
          Нет общих фото обхода
        </p>
      )}
    </div>
  )
}
