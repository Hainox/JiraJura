import { create } from 'zustand'

// Фильтры/вкладка/скролл карты — раньше жили в useState внутри MapPage и
// сбрасывались при каждом возврате на неё (открыл площадку из списка,
// нажал "назад" — фильтр района и вкладка "Проверка" слетали). Зустand-стор
// живёт вне дерева компонентов, поэтому переживает размонтирование
// страницы при переходе на другой роут и обратно.
interface MapViewState {
  viewMode: 'map' | 'list' | 'review'
  districtFilter?: string
  typeFilter?: string
  reviewStatusFilter: string
  myInspOnly: boolean
  myAssignedOnly: boolean
  listScrollTop: number
  setViewMode: (v: MapViewState['viewMode']) => void
  setDistrictFilter: (v?: string) => void
  setTypeFilter: (v?: string) => void
  setReviewStatusFilter: (v: string) => void
  setMyInspOnly: (v: boolean) => void
  setMyAssignedOnly: (v: boolean) => void
  setListScrollTop: (v: number) => void
  reset: () => void
}

const initial = {
  viewMode: 'map' as const,
  districtFilter: undefined,
  typeFilter: undefined,
  reviewStatusFilter: 'all',
  myInspOnly: false,
  myAssignedOnly: false,
  listScrollTop: 0,
}

export const useMapViewStore = create<MapViewState>((set) => ({
  ...initial,
  setViewMode: (viewMode) => set({ viewMode }),
  setDistrictFilter: (districtFilter) => set({ districtFilter }),
  setTypeFilter: (typeFilter) => set({ typeFilter }),
  setReviewStatusFilter: (reviewStatusFilter) => set({ reviewStatusFilter }),
  setMyInspOnly: (myInspOnly) => set({ myInspOnly }),
  setMyAssignedOnly: (myAssignedOnly) => set({ myAssignedOnly }),
  setListScrollTop: (listScrollTop) => set({ listScrollTop }),
  // На общем планшете в поле следующий залогинившийся не должен унаследовать
  // фильтры предыдущего инспектора/проверяющего — тот же принцип, что и у
  // force_pw_change в stores/auth.ts.
  reset: () => set(initial),
}))
