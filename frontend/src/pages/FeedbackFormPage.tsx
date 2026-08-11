import { useState, useRef } from 'react'
import { feedbackApi } from '@/lib/api'
import { notify as toast } from '@/lib/toast'
import type { FeedbackReportType } from '@/types'
import { MessageSquareWarning, CheckCircle2, MapPinned, Bug, HelpCircle, Paperclip, X, FileText } from 'lucide-react'

const TYPE_CONFIG: Record<FeedbackReportType, {
  label: string
  icon: React.ReactNode
  intro: string
  locationLabel: string | null
  locationPlaceholder: string
  messagePlaceholder: string
}> = {
  site: {
    label: 'Площадка/двор',
    icon: <MapPinned className="w-4 h-4" />,
    intro: 'Жалоба на состояние детской/спортивной площадки или двора.',
    locationLabel: 'Адрес / площадка (если знаете)',
    locationPlaceholder: 'Например: ул. Дубнинская 26к4',
    messagePlaceholder: 'Опишите, что не так на площадке',
  },
  app: {
    label: 'Проблема в приложении',
    icon: <Bug className="w-4 h-4" />,
    intro: 'Не получается войти, что-то не работает или не отображается в самом приложении.',
    locationLabel: 'Где возникло (страница / действие)',
    locationPlaceholder: 'Например: не могу войти / не открывается обход',
    messagePlaceholder: 'Опишите, что делали и что пошло не так',
  },
  other: {
    label: 'Другое',
    icon: <HelpCircle className="w-4 h-4" />,
    intro: 'Любое другое обращение, не связанное напрямую с площадкой или приложением.',
    locationLabel: null,
    locationPlaceholder: '',
    messagePlaceholder: 'Опишите обращение',
  },
}

// Синхронно с бэкендом (см. _ALLOWED_EXTENSIONS/_MAX_ATTACHMENTS_PER_REPORT
// в app/routers/feedback.py) — тут только для ранней обратной связи,
// реальная проверка всё равно на сервере.
const ALLOWED_EXT = ['jpg', 'jpeg', 'png', 'heic', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt']
const MAX_ATTACHMENTS = 5
const MAX_ATTACHMENT_MB = 20

function fileExt(name: string): string {
  return name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
}

export default function FeedbackFormPage() {
  const [type, setType] = useState<FeedbackReportType>('site')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [locationText, setLocationText] = useState('')
  const [message, setMessage] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const cfg = TYPE_CONFIG[type]

  const handleFilesPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (picked.length === 0) return

    const next = [...files]
    for (const f of picked) {
      if (next.length >= MAX_ATTACHMENTS) {
        toast.error(`Не больше ${MAX_ATTACHMENTS} файлов`)
        break
      }
      if (!ALLOWED_EXT.includes(fileExt(f.name))) {
        toast.error(`Неподдерживаемый тип файла: ${f.name}`)
        continue
      }
      if (f.size > MAX_ATTACHMENT_MB * 1024 * 1024) {
        toast.error(`${f.name} больше ${MAX_ATTACHMENT_MB} МБ`)
        continue
      }
      next.push(f)
    }
    setFiles(next)
  }

  const removeFile = (idx: number) => setFiles((prev) => prev.filter((_, i) => i !== idx))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (message.trim().length < 5) {
      toast.error('Опишите проблему чуть подробнее (минимум 5 символов)')
      return
    }
    setSubmitting(true)
    try {
      const report = await feedbackApi.submit({
        report_type: type,
        full_name: fullName.trim() || undefined,
        phone: phone.trim() || undefined,
        location_text: locationText.trim() || undefined,
        message: message.trim(),
      })

      // Обращение уже создано на сервере — если вложение не загрузится,
      // не откатываем и не блокируем: сообщаем и позволяем продолжить,
      // сама жалоба важнее приложенного файла.
      let failedCount = 0
      for (const f of files) {
        try {
          await feedbackApi.uploadAttachment(report.id, f)
        } catch {
          failedCount += 1
        }
      }
      if (failedCount > 0) {
        toast.error(`Обращение отправлено, но ${failedCount} файл(ов) не загрузилось`)
      }
      setSent(true)
    } catch {
      toast.error('Не удалось отправить — попробуйте ещё раз')
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    setSent(false); setType('site'); setFullName(''); setPhone(''); setLocationText(''); setMessage(''); setFiles([])
  }

  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-b from-blue-900 to-blue-700 px-4 overflow-y-auto py-8">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-2xl mb-4">
            <MessageSquareWarning className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Сообщить о проблеме</h1>
          <p className="text-blue-200 mt-1">Журнал обхода площадок САО</p>
        </div>

        <div className="card backdrop-blur-sm bg-white/95">
          {sent ? (
            <div className="text-center py-4">
              <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="text-gray-800 font-medium">Обращение принято</p>
              <p className="text-gray-500 text-sm mt-1">Спасибо, мы разберём его в ближайшее время.</p>
              <button type="button" className="btn-outline w-full mt-4" onClick={reset}>
                Отправить ещё одно
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label className="label">Тип обращения</label>
                <div className="grid grid-cols-3 gap-1.5">
                  {(Object.keys(TYPE_CONFIG) as FeedbackReportType[]).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setType(t)}
                      className={`flex flex-col items-center gap-1 py-2 px-1 rounded-lg text-xs font-medium border transition-colors ${
                        type === t
                          ? 'bg-primary-600 text-white border-primary-600'
                          : 'bg-white text-gray-600 border-gray-200 hover:border-primary-300'
                      }`}
                    >
                      {TYPE_CONFIG[t].icon}
                      {TYPE_CONFIG[t].label}
                    </button>
                  ))}
                </div>
              </div>

              <p className="mb-4 text-gray-600 text-sm">{cfg.intro} Можно отправить анонимно.</p>

              <div className="mb-4">
                <label className="label" htmlFor="full_name">ФИО (необязательно)</label>
                <input
                  id="full_name" type="text" className="input-field"
                  value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={200}
                />
              </div>
              <div className="mb-4">
                <label className="label" htmlFor="phone">Телефон для связи (необязательно)</label>
                <input
                  id="phone" type="tel" className="input-field"
                  value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={20}
                />
              </div>
              {cfg.locationLabel && (
                <div className="mb-4">
                  <label className="label" htmlFor="location">{cfg.locationLabel}</label>
                  <input
                    id="location" type="text" className="input-field"
                    placeholder={cfg.locationPlaceholder}
                    value={locationText} onChange={(e) => setLocationText(e.target.value)} maxLength={500}
                  />
                </div>
              )}
              <div className="mb-4">
                <label className="label" htmlFor="message">Что случилось *</label>
                <textarea
                  id="message" className="input-field min-h-[100px]"
                  placeholder={cfg.messagePlaceholder}
                  value={message} onChange={(e) => setMessage(e.target.value)}
                  minLength={5} maxLength={3000} required
                />
              </div>

              <div className="mb-6">
                <label className="label">Вложения (необязательно)</label>
                <p className="text-xs text-gray-400 mb-2">
                  Фото или файлы — например, скриншот ошибки или список проблемных пользователей. До {MAX_ATTACHMENTS} файлов, {MAX_ATTACHMENT_MB} МБ каждый.
                </p>
                {files.length > 0 && (
                  <div className="space-y-1.5 mb-2">
                    {files.map((f, i) => (
                      <div key={`${f.name}-${i}`} className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-2.5 py-1.5">
                        {f.type.startsWith('image/')
                          ? <Paperclip className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                          : <FileText className="w-3.5 h-3.5 text-gray-400 shrink-0" />}
                        <span className="text-xs text-gray-700 truncate flex-1">{f.name}</span>
                        <span className="text-[10px] text-gray-400 shrink-0">{(f.size / 1024 / 1024).toFixed(1)} МБ</span>
                        <button type="button" onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500 shrink-0">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {files.length < MAX_ATTACHMENTS && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="btn-outline w-full text-sm flex items-center justify-center gap-2"
                  >
                    <Paperclip className="w-4 h-4" /> Прикрепить файл
                  </button>
                )}
                <input
                  ref={fileInputRef} type="file" multiple hidden
                  accept={ALLOWED_EXT.map((e) => `.${e}`).join(',')}
                  onChange={handleFilesPicked}
                />
              </div>

              <button type="submit" disabled={submitting} className="btn-primary w-full">
                {submitting ? 'Отправляем…' : 'Отправить'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
