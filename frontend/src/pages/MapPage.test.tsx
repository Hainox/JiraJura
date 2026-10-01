import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MapPage from './MapPage'
import { useMapViewStore } from '@/stores/mapView'

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  logout: vi.fn(),
  user: { id: 'u1', full_name: 'Иванов И.И.', role: 'reviewer', district_id: 'd1' } as Record<string, unknown>,
}))

vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<object>('react-router-dom')),
  useNavigate: () => mocks.navigate,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) => selector({ user: mocks.user, logout: mocks.logout }),
}))

vi.mock('leaflet', () => ({
  default: {
    divIcon: (options: { html: string }) => options,
    latLngBounds: () => ({}),
  },
}))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  AttributionControl: () => null,
  Popup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Marker: ({ icon, children }: { icon: { html: string }; children: ReactNode }) => (
    <div data-testid="marker" data-html={icon.html}>{children}</div>
  ),
  useMap: () => ({ fitBounds: vi.fn(), setView: vi.fn() }),
}))

vi.mock('react-leaflet-cluster', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const sites = [
  { id: 'child-done', type: 'Детская площадка', lat: 55.8, lon: 37.5, area_m2: 100, courtyard: { name: 'Двор 1' }, district: { name: 'Район' } },
  { id: 'sport-new', type: 'Спортивная площадка', lat: 55.81, lon: 37.51, area_m2: 200, courtyard: { name: 'Двор 2' }, district: { name: 'Район' } },
]
const todayInspections = [
  { id: 'i1', site_id: 'child-done', status: 'completed', created_at: '2026-09-30T08:00:00Z', inspector: { full_name: 'Петров' } },
]

vi.mock('@/lib/api', () => ({
  sitesApi: { list: vi.fn(async () => ({ total: sites.length, items: sites })) },
  districtsApi: { list: vi.fn(async () => [{ id: 'd1', name: 'Район' }]) },
  reportsApi: { exportXlsx: vi.fn(async () => undefined) },
  inspectionsApi: {
    list: vi.fn(async () => ({ total: todayInspections.length, items: todayInspections })),
    update: vi.fn(),
    bulkAccept: vi.fn(),
  },
}))

function renderMap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <MapPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MapPage — шапка', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useMapViewStore.setState({ viewMode: 'map', myInspOnly: false, myAssignedOnly: false, typeFilter: undefined })
  })

  it('у района подписанные кнопки, а профиль и выход — в меню «Ещё»', async () => {
    mocks.user = { id: 'u1', full_name: 'Иванов И.И.', role: 'reviewer', district_id: 'd1' }
    const user = userEvent.setup()
    renderMap()

    const nav = screen.getByRole('navigation', { name: 'Разделы' })
    for (const label of ['Статистика', 'Замечания', 'Фильтры', 'Помощь']) {
      expect(within(nav).getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(screen.queryByRole('menuitem', { name: 'Выйти' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ещё' }))
    expect(screen.getByRole('button', { name: 'Ещё' })).toHaveAttribute('aria-expanded', 'true')
    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Профиль' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Выгрузка в Excel' })).toBeInTheDocument()

    await user.click(within(menu).getByRole('menuitem', { name: 'Выйти' }))
    expect(mocks.logout).toHaveBeenCalled()
    expect(mocks.navigate).toHaveBeenCalledWith('/login')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('у инспектора «История» и «Помощь», выгрузки в меню нет', async () => {
    mocks.user = { id: 'u2', full_name: 'Сидоров С.С.', role: 'inspector', district_id: 'd1' }
    const user = userEvent.setup()
    renderMap()

    await user.click(screen.getByRole('button', { name: 'История' }))
    expect(mocks.navigate).toHaveBeenCalledWith('/my-inspections')
    await user.click(screen.getByRole('button', { name: 'Помощь' }))
    expect(mocks.navigate).toHaveBeenCalledWith('/help')

    await user.click(screen.getByRole('button', { name: 'Ещё' }))
    expect(screen.queryByRole('menuitem', { name: 'Выгрузка в Excel' })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it.each(['inspector', 'reviewer', 'admin'])('у роли %s в шапке есть переход в «Люки САО»', async (role) => {
    mocks.user = { id: 'u4', full_name: 'Сотрудник', role, district_id: role === 'admin' ? undefined : 'd1' }
    const user = userEvent.setup()
    renderMap()

    const link = screen.getByRole('link', { name: /Люки САО/ })
    expect(link).toHaveAttribute('href', 'https://luki.obhod-sao.ru')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')

    await user.click(screen.getByRole('button', { name: 'Ещё' }))
    expect(within(screen.getByRole('menu')).queryByRole('menuitem', { name: 'Люки САО' })).not.toBeInTheDocument()
  })

  it('у округа кнопка «Управление» ведёт в админ-панель', async () => {
    mocks.user = { id: 'u3', full_name: 'Админ', role: 'admin' }
    const user = userEvent.setup()
    renderMap()
    await user.click(screen.getByRole('button', { name: 'Управление' }))
    expect(mocks.navigate).toHaveBeenCalledWith('/admin')
  })
})

describe('MapPage — легенда и метки', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.user = { id: 'u2', full_name: 'Сидоров С.С.', role: 'inspector', district_id: 'd1' }
    useMapViewStore.setState({ viewMode: 'map', myInspOnly: false, myAssignedOnly: false, typeFilter: undefined })
  })

  it('легенда и счётчик видны над картой без открытия фильтров', async () => {
    renderMap()
    const legend = await screen.findByRole('group', { name: 'Легенда карты' })
    for (const label of ['Не обойдена', 'В процессе', 'Завершена', 'С нарушениями']) {
      expect(within(legend).getByText(label)).toBeInTheDocument()
    }
    expect(await within(legend).findByText('Сегодня обойдено: 1/2')).toBeInTheDocument()
  })

  it('необойдённая спортивная площадка — синяя, как «Не обойдена», а не зелёная', async () => {
    renderMap()
    await screen.findByText('Сегодня обойдено: 1/2')
    const markers = await screen.findAllByTestId('marker')
    const sportMarker = markers.find((m) => m.textContent?.includes('Двор 2'))!
    const doneMarker = markers.find((m) => m.textContent?.includes('Двор 1'))!
    expect(sportMarker.dataset.html).toContain('background:#2563eb')
    expect(sportMarker.dataset.html).toContain('>С<')
    expect(doneMarker.dataset.html).toContain('background:#16a34a')
  })
})
