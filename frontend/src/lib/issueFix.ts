import type { IssueOut, PhotoOut } from '@/types'

// Сервер отдаёт время с микросекундами; разбирать больше трёх знаков
// после точки движок не обязан (стандарт описывает только миллисекунды) —
// обрезаем, чтобы старый Safari не получил NaN.
function parseTime(value: string): number {
  return Date.parse(value.replace(/(\.\d{3})\d+/, '$1'))
}

/** Фото исправления, которые сервер засчитает при переводе в «Исправлено».
 *
 * После возврата на доработку сервер принимает только снимки, загруженные
 * не раньше последнего перехода в revision_needed (issues.py, update_issue:
 * Photo.created_at >= IssueStatusHistory.created_at). Время перехода клиенту
 * не отдаётся, но тот же PUT, что возвращает карточку, проставляет
 * updated_at на миллисекунды раньше записи в истории — берём его. Более
 * поздняя правка карточки (срок, назначение) сдвинет updated_at вперёд, и
 * тогда UI попросит новое фото строже сервера, но никогда не наоборот: UI
 * не должен говорить «готово», когда сервер откажет. */
export function acceptableFixPhotos(
  issue: Pick<IssueOut, 'status' | 'updated_at' | 'fix_photos'>,
): PhotoOut[] {
  const photos = issue.fix_photos ?? []
  if (issue.status !== 'revision_needed') return photos
  const returnedAt = issue.updated_at ? parseTime(issue.updated_at) : NaN
  // Не с чем сравнить — пусть решает сервер (он ответит понятной ошибкой),
  // а не вечная серая кнопка без выхода.
  if (Number.isNaN(returnedAt)) return photos
  return photos.filter((photo) => {
    const uploadedAt = parseTime(photo.created_at)
    return Number.isNaN(uploadedAt) || uploadedAt >= returnedAt
  })
}
