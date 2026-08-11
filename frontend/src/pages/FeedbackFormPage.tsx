import { useState } from 'react'
import { feedbackApi } from '@/lib/api'
import { notify as toast } from '@/lib/toast'
import { MessageSquareWarning, CheckCircle2 } from 'lucide-react'

export default function FeedbackFormPage() {
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [locationText, setLocationText] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (message.trim().length < 5) {
      toast.error('Опишите проблему чуть подробнее (минимум 5 символов)')
      return
    }
    setSubmitting(true)
    try {
      await feedbackApi.submit({
        full_name: fullName.trim() || undefined,
        phone: phone.trim() || undefined,
        location_text: locationText.trim() || undefined,
        message: message.trim(),
      })
      setSent(true)
    } catch {
      toast.error('Не удалось отправить — попробуйте ещё раз')
    } finally {
      setSubmitting(false)
    }
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
              <button
                type="button"
                className="btn-outline w-full mt-4"
                onClick={() => { setSent(false); setFullName(''); setPhone(''); setLocationText(''); setMessage('') }}
              >
                Отправить ещё одно
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <p className="mb-4 text-gray-600 text-sm">
                Форма для жалоб и обращений по детским и спортивным площадкам округа. Можно отправить анонимно.
              </p>
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
              <div className="mb-4">
                <label className="label" htmlFor="location">Адрес / площадка (если знаете)</label>
                <input
                  id="location" type="text" className="input-field"
                  placeholder="Например: ул. Дубнинская 26к4"
                  value={locationText} onChange={(e) => setLocationText(e.target.value)} maxLength={500}
                />
              </div>
              <div className="mb-6">
                <label className="label" htmlFor="message">Что случилось *</label>
                <textarea
                  id="message" className="input-field min-h-[100px]"
                  value={message} onChange={(e) => setMessage(e.target.value)}
                  minLength={5} maxLength={3000} required
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
