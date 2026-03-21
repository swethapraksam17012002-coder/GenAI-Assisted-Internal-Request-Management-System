import { create } from 'zustand'

export const useAuthStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('nexus_access_token'),
  loading: true,

  setUser: user => set({ user }),
  setToken: token => {
    localStorage.setItem('nexus_access_token', token)
    set({ token })
  },
  logout: () => {
    localStorage.removeItem('nexus_access_token')
    localStorage.removeItem('nexus_refresh_token')
    set({ user: null, token: null })
  },
  setLoading: loading => set({ loading }),
}))

export const useUIStore = create((set) => ({
  sidebarCollapsed: false,
  toasts: [],
  toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  addToast: (msg, type = 'success') => {
    const id = Date.now()
    set(s => ({ toasts: [...s.toasts, { id, msg, type }] }))
    setTimeout(() => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })), 4000)
  },
  removeToast: id => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))
