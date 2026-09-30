import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, ChevronRight, CircleDot } from 'lucide-react'
import { describeInspectionUpdateError, hatchesApi, issuesApi } from '@/lib/api'
import { usePhotoUpload } from '@/lib/usePhotoUpload'
import { notify as toast } from '@/lib/toast'
import {
  HATCH_STATES, HATCH_STATE_FULL, HATCH_STATE_PILL, HATCH_STATE_SHORT, hatchTitle, inspectionHatchesKey, mskTime, ruDate,
} from '@/lib/hatches'
import type { HatchCheckIn, HatchCheckOut, HatchState, InspectionHatchOut } from '@/types'

// Автоповтор отправки фото — как uploadPhotoWithRetry в InspectionPage:
// связь в поле «плавает», большинство сбоев чинятся сами за пару секунд.
async function uploadWithRetry(issueId: string, file: File, attempts = 3) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await issuesApi.uploadPhoto(issueId, file)
    } catch (err) {
      if (attempt >= attempts) throw err
      await new Promise((resolve) => setTimeout(resolve, attempt * 1500))
    }
  }
}

export default function HatchChecksBlock({ inspectionId, editable }: { inspectionId: string; editable: boolean }) {
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const { data: items } = useQuery({
    queryKey: inspectionHatchesKey(inspectionId),
    queryFn: () => hatchesApi.forInspection(inspectionId),
  })

  const afterChange = () => {
    // Дефект люка создаёт/удаляет замечание обхода на сервере — список
    // «Замечания по обходу» и счётчик в шапке должны это увидеть.
    queryClient.invalidateQueries({ queryKey: ['issues', inspectionId] })
    queryClient.invalidateQueries({ queryKey: ['inspection', inspectionId] })
  }

  const saveMutation = useMutation({
    mutationFn: ({ hatchId, body }: { hatchId: string; body: HatchCheckIn }) =>
      hatchesApi.saveCheck(inspectionId, hatchId, body),
    onSuccess: (check) => {
      queryClient.setQueryData<InspectionHatchOut[]>(inspectionHatchesKey(inspectionId), (old) =>
        old?.map((i) => (i.hatch.id === check.hatch_id ? { ...i, check } : i)))
      afterChange()
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
  })

  const allOkMutation = useMutation({
    mutationFn: () => hatchesApi.markRemainingOk(inspectionId),
    onSuccess: (fresh) => {
      queryClient.setQueryData(inspectionHatchesKey(inspectionId), fresh)
      toast.success('Остальные люки отмечены исправными')
    },
    onError: (err) => toast.error(describeInspectionUpdateError(err)),
  })

  if (!items || items.length === 0) return null

  const marked = items.filter((i) => i.check).length
  const unmarked = items.filter((i) => i.hatch.is_active && !i.check).length
  const save = (hatchId: string, body: HatchCheckIn) => saveMutation.mutateAsync({ hatchId, body }).catch(() => undefined)

  return (
    <section className="card space-y-3" aria-label="Люки">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="font-bold text-gray-800">Люки</h2>
          <div className={`text-sm ${marked === items.length ? 'text-green-700' : 'text-gray-500'}`}>
            Люки: отмечено {marked} из {items.length}
          </div>
        </div>
        <CircleDot className="w-5 h-5 text-gray-400" />
      </div>

      <div className="space-y-2">
        {items.map((item) => (
          <HatchRow
            key={item.hatch.id}
            item={item}
            editable={editable}
            expanded={expandedId === item.hatch.id}
            onToggle={() => setExpandedId((cur) => (cur === item.hatch.id ? null : item.hatch.id))}
            onSave={(body) => save(item.hatch.id, body)}
            saving={saveMutation.isPending && saveMutation.variables?.hatchId === item.hatch.id}
            onPhotoUploaded={() => queryClient.invalidateQueries({ queryKey: inspectionHatchesKey(inspectionId) })}
          />
        ))}
      </div>

      {editable && unmarked > 0 && (
        <button
          type="button"
          onClick={() => allOkMutation.mutate()}
          disabled={allOkMutation.isPending}
          className="btn-primary w-full py-3 text-base flex items-center justify-center gap-2 disabled:opacity-60"
        >
          <CheckCircle2 className="w-5 h-5" />
          {allOkMutation.isPending ? 'Отмечаем…' : 'Остальные люки исправны'}
        </button>
      )}
    </section>
  )
}

function HatchRow({
  item, editable, expanded, onToggle, onSave, saving, onPhotoUploaded,
}: {
  item: InspectionHatchOut
  editable: boolean
  expanded: boolean
  onToggle: () => void
  onSave: (body: HatchCheckIn) => Promise<unknown>
  saving: boolean
  onPhotoUploaded: () => void
}) {
  const { hatch, check } = item
  const isDefect = !!check && check.state !== 'ok'
  const [ticket, setTicket] = useState(check?.owner_ticket ?? '')
  const [comment, setComment] = useState(check?.comment ?? '')
  const photoInputRef = useRef<HTMLInputElement>(null)

  // Черновики полей подтягиваются с сервера после каждого сохранения
  // (например, «Остальные люки исправны» или правка с другого устройства).
  useEffect(() => { setTicket(check?.owner_ticket ?? '') }, [check?.owner_ticket])
  useEffect(() => { setComment(check?.comment ?? '') }, [check?.comment])

  const body = (overrides: Partial<HatchCheckIn>): HatchCheckIn => ({
    state: check?.state ?? 'ok',
    fenced: check?.fenced ?? false,
    owner_ticket: ticket.trim() || null,
    comment: comment.trim() || null,
    ...overrides,
  })

  const chooseState = (state: HatchState) => {
    if (!editable || saving) return
    onSave(state === 'ok'
      ? { state, comment: comment.trim() || null }
      : body({ state }))
  }

  const saveTextIfChanged = () => {
    if (!editable || !check) return
    if ((check.owner_ticket ?? '') === ticket.trim() && (check.comment ?? '') === comment.trim()) return
    onSave(body({}))
  }

  const { isUploading, handleFileInput } = usePhotoUpload(async (file: File) => {
    if (!check?.issue_id) return
    await uploadWithRetry(check.issue_id, file)
    onPhotoUploaded()
    toast.success('Фото нарушения сохранено')
  })

  return (
    <div className={`rounded-xl border ${isDefect ? 'border-red-200' : 'border-gray-200'} ${expanded ? 'ring-2 ring-primary-100' : ''}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full min-h-11 px-3 py-2.5 flex items-center gap-3 text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-gray-800">{hatchTitle(hatch)}</div>
          {hatch.location_note && <div className="text-xs text-gray-500 truncate">{hatch.location_note}</div>}
        </div>
        {check ? (
          <div className="flex flex-col items-end gap-0.5 shrink-0">
            <span className={`badge text-xs ${HATCH_STATE_PILL[check.state]}`}>{HATCH_STATE_SHORT[check.state]}</span>
            <span className="text-[11px] text-gray-400">{mskTime(check.updated_at ?? check.created_at)}</span>
          </div>
        ) : (
          <span className="badge text-xs bg-gray-100 text-gray-500 shrink-0">не отмечен</span>
        )}
        {expanded ? <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-gray-100 pt-3">
          {editable ? (
            <div className="grid gap-2" role="radiogroup" aria-label={`Состояние: ${hatchTitle(hatch)}`}>
              {HATCH_STATES.map((state) => {
                const selected = check?.state === state
                const tone = state === 'ok'
                  ? selected ? 'bg-green-600 text-white border-green-600' : 'bg-green-50 text-green-800 border-green-200'
                  : selected ? 'bg-red-600 text-white border-red-600' : 'bg-white text-red-800 border-red-200'
                return (
                  <button
                    key={state}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => chooseState(state)}
                    disabled={saving}
                    className={`min-h-11 w-full rounded-xl border-2 px-3 py-2 text-left text-sm font-semibold transition-colors disabled:opacity-60 ${tone}`}
                  >
                    {selected && '✓ '}{HATCH_STATE_FULL[state]}
                  </button>
                )
              })}
            </div>
          ) : !check ? (
            <div className="text-sm text-gray-500">Люк не отмечен в этом обходе.</div>
          ) : !isDefect && check.checked_by_name ? (
            <div className="text-xs text-gray-500">Осмотрел: {check.checked_by_name}</div>
          ) : null}

          {isDefect && check && (
            <div className="space-y-3">
              <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 text-xs text-red-800 flex gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  {check.issue_id
                    ? <>Создано критическое замечание «Люки» со сроком 1 день{check.issue_due_date ? ` (до ${ruDate(check.issue_due_date)})` : ''}. </>
                    : <>Будет создано критическое замечание «Люки» со сроком 1 день. </>}
                  Устранение и приёмка — как по площадкам.
                </span>
              </div>

              <div>
                <div className="text-xs font-semibold text-gray-600 mb-1.5">
                  Фото нарушения {check.photos.length === 0 && <span className="text-red-600">— обязательно</span>}
                </div>
                {check.photos.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {check.photos.map((p, index) => (
                      <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                        <img src={p.thumbnail_url ?? p.url} alt={`Фото люка ${index + 1}`} className="w-16 h-16 object-cover rounded-lg border" />
                      </a>
                    ))}
                  </div>
                )}
                {editable && check.issue_id && (
                  <>
                    <input ref={photoInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileInput} />
                    <button
                      type="button"
                      onClick={() => photoInputRef.current?.click()}
                      disabled={isUploading}
                      className="w-full min-h-11 rounded-xl font-bold text-sm bg-red-50 text-red-700 border-2 border-red-200 hover:bg-red-100 flex items-center justify-center gap-2 disabled:opacity-60"
                    >
                      <Camera className="w-5 h-5" />
                      {isUploading ? 'Загружаем фото…' : check.photos.length ? 'Добавить ещё фото' : 'Добавить фото нарушения'}
                    </button>
                  </>
                )}
              </div>

              {editable ? (
                <>
                  <label className="flex items-center gap-2 min-h-11 text-sm text-gray-800">
                    <input
                      type="checkbox"
                      className="w-5 h-5"
                      checked={!!check.fenced}
                      disabled={saving}
                      onChange={(e) => onSave(body({ fenced: e.target.checked }))}
                    />
                    Опасное место ограждено
                  </label>
                  <input
                    className="input-field text-sm"
                    placeholder="№ заявки владельцу люка"
                    aria-label="№ заявки владельцу люка"
                    value={ticket}
                    maxLength={100}
                    onChange={(e) => setTicket(e.target.value)}
                    onBlur={saveTextIfChanged}
                  />
                  <textarea
                    className="input-field text-sm"
                    rows={2}
                    placeholder="Комментарий"
                    aria-label="Комментарий к люку"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    onBlur={saveTextIfChanged}
                  />
                </>
              ) : (
                <HatchMeasures check={check} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function HatchMeasures({ check }: { check: HatchCheckOut }) {
  return (
    <div className="text-xs text-gray-600 space-y-0.5">
      <div>{check.fenced ? 'Опасное место ограждено' : 'Опасное место не ограждено'}</div>
      {check.owner_ticket && <div>Заявка владельцу № {check.owner_ticket}</div>}
      {check.comment && <div>{check.comment}</div>}
      {check.checked_by_name && <div className="text-gray-400">Осмотрел: {check.checked_by_name}</div>}
    </div>
  )
}
