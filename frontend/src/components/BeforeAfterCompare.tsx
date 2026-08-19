interface Props {
  /** URL фото ДО (из обхода) */
  beforeUrl?: string
  /** URL фото ПОСЛЕ (исправления) */
  afterUrl?: string
  /** Метка левой стороны */
  beforeLabel?: string
  /** Метка правой стороны */
  afterLabel?: string
  /** Открыть фото во весь экран (лайтбокс родителя) — без него фото
   * открывалось бы target="_blank" голой ссылкой, что в PWA standalone на
   * iOS Safari уводит с картинки без возможности закрыть её. */
  onPhotoClick: (url: string) => void
}

/** Одно окошко ДО или ПОСЛЕ: подпись + фото целиком (object-contain, не
 * cover) на тёмной подложке — без этого узкий/широкий телефонный кадр
 * обрезался бы под фиксированную коробку и терял как раз то место, где
 * видно нарушение или исправление. */
function Panel({ url, label, dotColor, onPhotoClick }: { url?: string; label: string; dotColor: string; onPhotoClick: (url: string) => void }) {
  return (
    <div className="space-y-1.5">
      <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2 py-0.5 rounded-full ${dotColor}`}>
        {label}
      </span>
      {url ? (
        <button onClick={() => onPhotoClick(url)} className="block w-full h-56 bg-gray-900 rounded-xl overflow-hidden hover:opacity-90 transition-opacity">
          <img src={url} alt={label} className="w-full h-full object-contain" />
        </button>
      ) : (
        <div className="w-full h-56 bg-gray-100 rounded-xl flex items-center justify-center text-gray-400 text-xs text-center px-3">
          {label === 'ДО' ? 'Фото ДО отсутствует' : 'Фото ПОСЛЕ ещё не загружено'}
        </div>
      )}
    </div>
  )
}

/** Сравнение ДО/ПОСЛЕ двумя отдельными окошками рядом — раньше был
 * слайдер-шторка, но при разных пропорциях фото (что для телефонных
 * снимков обычное дело) он давал либо обрезанные, либо перекошенные
 * кадры вместо адекватного сравнения. */
export default function BeforeAfterCompare({
  beforeUrl,
  afterUrl,
  beforeLabel = 'ДО',
  afterLabel = 'ПОСЛЕ',
  onPhotoClick,
}: Props) {
  if (!beforeUrl && !afterUrl) {
    return (
      <div className="bg-gray-100 rounded-xl flex items-center justify-center h-48 text-gray-400 text-sm">
        Нет фото для сравнения
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <Panel url={beforeUrl} label={beforeLabel} dotColor="bg-blue-100 text-blue-700" onPhotoClick={onPhotoClick} />
      <Panel url={afterUrl} label={afterLabel} dotColor="bg-green-100 text-green-700" onPhotoClick={onPhotoClick} />
    </div>
  )
}
