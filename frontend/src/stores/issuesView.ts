import { create } from 'zustand'

// Фильтры/страница списка замечаний — раньше жили в useState внутри
// IssuesPage и сбрасывались при каждом возврате на страницу (открыл обход
// по замечанию, нажал "назад" — фильтр района/статуса и номер страницы
// слетали на дефолт). См. тот же паттерн в stores/mapView.ts.
interface IssuesViewState {
  statusFilter: string
  criticalityFilter: string
  districtFilter: string
  searchTerm: string
  page: number
  setStatusFilter: (v: string) => void
  setCriticalityFilter: (v: string) => void
  setDistrictFilter: (v: string) => void
  setSearchTerm: (v: string) => void
  setPage: (v: number | ((p: number) => number)) => void
  reset: () => void
}

const initial = {
  statusFilter: '',
  criticalityFilter: '',
  districtFilter: '',
  searchTerm: '',
  page: 1,
}

export const useIssuesViewStore = create<IssuesViewState>((set, get) => ({
  ...initial,
  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setCriticalityFilter: (criticalityFilter) => set({ criticalityFilter }),
  setDistrictFilter: (districtFilter) => set({ districtFilter }),
  setSearchTerm: (searchTerm) => set({ searchTerm }),
  setPage: (v) => set({ page: typeof v === 'function' ? v(get().page) : v }),
  // Общее устройство в поле — см. reset() в stores/mapView.ts.
  reset: () => set(initial),
}))
