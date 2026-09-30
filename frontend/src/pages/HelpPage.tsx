import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ChevronDown, MessageSquareWarning, Search, X } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { FAQ_ROLE_CHIPS, FAQ_TOPICS, filterFaq, type FaqRoleFilter } from '@/lib/faq'
import { ROLES } from '@/lib/roles'

const topicDomId = (topicId: string) => `faq-topic-${topicId}`

// Ссылка вида /help?topic=stat у инспектора иначе открыла бы пустую
// страницу: его роль по умолчанию скрыла бы все вопросы этой темы.
function initialRole(rawRole: string | undefined, deepTopic: string | null): FaqRoleFilter {
  const userRole = ROLES.find((r) => r === rawRole)
  if (!userRole) return 'all'
  if (deepTopic && filterFaq(FAQ_TOPICS, userRole, '').every((t) => t.id !== deepTopic)) return 'all'
  return userRole
}

export default function HelpPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const deepTopic = searchParams.get('topic')

  const [role, setRole] = useState<FaqRoleFilter>(() => initialRole(user?.role, deepTopic))
  const [query, setQuery] = useState('')
  const [openTopics, setOpenTopics] = useState<Set<string>>(() => new Set(deepTopic ? [deepTopic] : []))
  const [openItems, setOpenItems] = useState<Set<string>>(() => new Set())

  const topics = useMemo(() => filterFaq(FAQ_TOPICS, role, query), [role, query])
  const isSearching = query.trim().length > 0

  useEffect(() => {
    if (!deepTopic) return
    setOpenTopics((prev) => (prev.has(deepTopic) ? prev : new Set(prev).add(deepTopic)))
    document.getElementById(topicDomId(deepTopic))?.scrollIntoView?.({ block: 'start' })
  }, [deepTopic])

  const toggle = (setter: typeof setOpenTopics, key: string) => {
    setter((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // key === 'default' — это первая запись истории (Помощь открыли по прямой
  // ссылке или из закладки): navigate(-1) увёл бы из приложения совсем.
  const goBack = () => {
    if (location.key !== 'default') navigate(-1)
    else navigate(user ? '/' : '/login')
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-primary-800 text-white px-4 py-2 flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={goBack}
          aria-label="Назад"
          className="-ml-2 flex h-11 w-11 items-center justify-center rounded-lg hover:bg-primary-700 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="min-w-0">
          <h1 className="text-lg font-bold">Помощь</h1>
          <p className="text-blue-200 text-xs">Ответы на частые вопросы</p>
        </div>
      </div>

      <div className="overflow-y-auto flex-1">
        <div className="max-w-2xl mx-auto p-4 space-y-4">
          <div className="space-y-3">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              <input
                type="search"
                className="input-field !pl-9 !pr-11 [&::-webkit-search-cancel-button]:hidden"
                placeholder="Поиск: пароль, фото, срок…"
                aria-label="Поиск по вопросам"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {isSearching && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  aria-label="Очистить поиск"
                  className="absolute right-0 top-1/2 -translate-y-1/2 flex h-11 w-11 items-center justify-center text-gray-400 hover:text-gray-600"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            <div>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Для кого вопросы">
                {FAQ_ROLE_CHIPS.map((chip) => (
                  <button
                    key={chip.value}
                    type="button"
                    aria-pressed={role === chip.value}
                    onClick={() => setRole(chip.value)}
                    className={`min-h-11 px-3 rounded-full text-sm font-medium transition-colors ${
                      role === chip.value
                        ? 'bg-primary-700 text-white'
                        : 'bg-white border border-gray-200 text-gray-700 hover:border-primary-300'
                    }`}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                «Район» — роль «Проверяющий» в приложении, «Округ» — администратор округа.
              </p>
            </div>
          </div>

          {topics.length === 0 ? (
            <div className="card text-center space-y-3" role="status">
              <p className="text-gray-700">Ничего не нашлось. Попробуйте другое слово или напишите нам — ответим.</p>
              <button
                type="button"
                onClick={() => navigate('/feedback')}
                data-prefetch="/feedback"
                className="btn-outline min-h-11 inline-flex items-center gap-2"
              >
                <MessageSquareWarning className="w-4 h-4" />
                Написать в поддержку
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {topics.map((topic) => {
                const topicOpen = isSearching || openTopics.has(topic.id)
                const panelId = `${topicDomId(topic.id)}-panel`
                return (
                  <section key={topic.id} id={topicDomId(topic.id)} className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden scroll-mt-4">
                    <h2>
                      <button
                        type="button"
                        aria-expanded={topicOpen}
                        aria-controls={panelId}
                        onClick={() => toggle(setOpenTopics, topic.id)}
                        className="w-full min-h-12 px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-gray-50 transition-colors"
                      >
                        <span className="font-semibold text-gray-800">{topic.title}</span>
                        <span className="flex items-center gap-2 text-xs text-gray-400 shrink-0">
                          {topic.items.length}
                          <ChevronDown className={`w-5 h-5 transition-transform ${topicOpen ? 'rotate-180' : ''}`} />
                        </span>
                      </button>
                    </h2>
                    {topicOpen && (
                      <ul id={panelId} className="border-t border-gray-100 divide-y divide-gray-100">
                        {topic.items.map((item, index) => {
                          const itemKey = `${topic.id}:${item.q}`
                          const itemOpen = openItems.has(itemKey)
                          const answerId = `${topicDomId(topic.id)}-a${index}`
                          return (
                            <li key={itemKey}>
                              <button
                                type="button"
                                aria-expanded={itemOpen}
                                aria-controls={answerId}
                                onClick={() => toggle(setOpenItems, itemKey)}
                                className="w-full min-h-11 px-4 py-3 flex items-start justify-between gap-3 text-left text-sm font-medium text-gray-800 hover:bg-gray-50 transition-colors"
                              >
                                <span>{item.q}</span>
                                <ChevronDown className={`w-4 h-4 mt-0.5 shrink-0 text-gray-400 transition-transform ${itemOpen ? 'rotate-180' : ''}`} />
                              </button>
                              {itemOpen && (
                                <div id={answerId} className="px-4 pb-4 -mt-1 text-sm leading-relaxed text-gray-600">
                                  {item.a}
                                </div>
                              )}
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </section>
                )
              })}
            </div>
          )}

          <div className="card flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="flex items-start gap-3 flex-1">
              <div className="w-10 h-10 rounded-full bg-primary-50 flex items-center justify-center shrink-0">
                <MessageSquareWarning className="w-5 h-5 text-primary-700" />
              </div>
              <div>
                <div className="font-semibold text-gray-800">Не нашли ответ?</div>
                <div className="text-sm text-gray-500">Опишите проблему — можно без входа в приложение и приложить скриншот.</div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate('/feedback')}
              data-prefetch="/feedback"
              className="btn-primary min-h-11 shrink-0"
            >
              Написать в поддержку
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
