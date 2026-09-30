import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Menu } from 'lucide-react'

export interface MoreMenuItem {
  label: string
  icon: ReactNode
  onSelect: () => void
  danger?: boolean
  prefetch?: string
}

/** Выпадающее меню «Ещё» для шапки: редкие действия (профиль, выгрузка,
 * выход), которым не хватает места в строке кнопок на телефоне 360 px. */
export default function MoreMenu({ items }: { items: MoreMenuItem[] }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    // capture: Leaflet гасит всплытие части событий внутри карты, и тап по
    // карте иначе не закрывал бы меню.
    const onPointerDown = (e: Event) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeyDown)
    rootRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`min-h-11 px-3 flex items-center gap-1.5 rounded-lg text-sm font-medium transition-colors ${
          open ? 'bg-primary-700' : 'hover:bg-primary-700'
        }`}
      >
        <Menu className="w-5 h-5" />
        Ещё
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Ещё"
          className="absolute right-0 top-full mt-1 z-[1100] min-w-52 rounded-xl border border-gray-100 bg-white py-1 text-gray-800 shadow-lg"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              data-prefetch={item.prefetch}
              onClick={() => {
                setOpen(false)
                item.onSelect()
              }}
              className={`w-full min-h-11 px-4 flex items-center gap-3 text-left text-sm hover:bg-gray-50 focus:bg-gray-50 focus:outline-none ${
                item.danger ? 'text-red-600' : ''
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
