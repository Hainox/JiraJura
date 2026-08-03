import { create } from 'zustand'

export interface OfflineAction {
  id: string
  type: 'check_item' | 'add_photo' | 'create_issue' | 'complete_inspection'
  payload: Record<string, unknown>
  created_at: string
  synced: boolean
}

interface OfflineState {
  queue: OfflineAction[]
  isOnline: boolean
  addToQueue: (action: Omit<OfflineAction, 'id' | 'created_at' | 'synced'>) => void
  removeFromQueue: (id: string) => void
  markSynced: (id: string) => void
  setOnline: (online: boolean) => void
}

const genId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

export const useOfflineStore = create<OfflineState>((set, get) => ({
  queue: [],
  isOnline: navigator.onLine,

  addToQueue: (action) => {
    const item: OfflineAction = {
      ...action,
      id: genId(),
      created_at: new Date().toISOString(),
      synced: false,
    }
    set((s) => ({ queue: [...s.queue, item] }))
    localStorage.setItem('offline_queue', JSON.stringify([...get().queue, item]))
  },

  removeFromQueue: (id) => {
    set((s) => {
      const next = s.queue.filter((a) => a.id !== id)
      localStorage.setItem('offline_queue', JSON.stringify(next))
      return { queue: next }
    })
  },

  markSynced: (id) => {
    set((s) => {
      const next = s.queue.map((a) => (a.id === id ? { ...a, synced: true } : a))
      localStorage.setItem('offline_queue', JSON.stringify(next))
      return { queue: next }
    })
  },

  setOnline: (online) => set({ isOnline: online }),
}))
