import axios from 'axios'

const BASE = 'http://localhost:8000'

export const http = axios.create({
  baseURL: BASE,
  timeout: 60000,
})

// ── Attach JWT on every request ───────────────────────────────────────────────
http.interceptors.request.use(cfg => {
  const token = localStorage.getItem('nexus_access_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  cfg.headers['X-Request-ID'] = crypto.randomUUID()
  return cfg
})

// ── Auto-refresh on 401 ───────────────────────────────────────────────────────
let refreshing = false
let queue = []

http.interceptors.response.use(
  r => r,
  async err => {
    const orig = err.config
    if (err.response?.status === 401 && !orig._retry) {
      if (refreshing) {
        return new Promise((res, rej) =>
          queue.push({ res, rej })
        ).then(token => {
          orig.headers.Authorization = `Bearer ${token}`
          return http(orig)
        })
      }
      orig._retry = true
      refreshing = true
      const refresh = localStorage.getItem('nexus_refresh_token')
      if (!refresh) { clearAuth(); return Promise.reject(err) }
      try {
        const { data } = await axios.post(`${BASE}/api/auth/refresh`, { refresh_token: refresh })
        localStorage.setItem('nexus_access_token', data.access_token)
        localStorage.setItem('nexus_refresh_token', data.refresh_token)
        queue.forEach(q => q.res(data.access_token))
        queue = []
        orig.headers.Authorization = `Bearer ${data.access_token}`
        return http(orig)
      } catch (e) {
        queue.forEach(q => q.rej(e))
        queue = []
        clearAuth()
        return Promise.reject(e)
      } finally { refreshing = false }
    }
    return Promise.reject(err)
  }
)

export function clearAuth() {
  localStorage.removeItem('nexus_access_token')
  localStorage.removeItem('nexus_refresh_token')
  window.location.href = '/login'
}

export const API = {
  // Auth
  login: (email, password) => {
    const form = new URLSearchParams({ username: email, password, grant_type: 'password' })
    return axios.post(`${BASE}/api/auth/token`, form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
  },
  register: body => http.post('/api/auth/register', body),
  me: () => http.get('/api/auth/me'),
  logout: () => http.post('/api/auth/logout'),
  refresh: rt => axios.post(`${BASE}/api/auth/refresh`, { refresh_token: rt }),
  csrfToken: () => http.get('/api/auth/csrf-token'),
  googleLoginUrl: () => `${BASE}/api/auth/google/login`,

  // Requests
  listRequests: params => http.get('/api/requests/', { params, timeout: 120000 }),
  getRequest: id => http.get(`/api/requests/${id}`, { timeout: 60000 }),
  createRequest: body => http.post('/api/requests/', body, { timeout: 120000 }),
  createDraftFromText: body => http.post('/api/requests/draft-from-text', body, { timeout: 180000 }),
  createDraftFromFormJson: body => http.post('/api/requests/draft-from-form-json', body, { timeout: 180000 }),
  updateRequest: (id, body) => http.patch(`/api/requests/${id}`, body),
  deleteRequest: id => http.delete(`/api/requests/${id}`),
  reviewRequest: (id, body) => http.post(`/api/requests/${id}/review`, body),
  approveRequest: (id, body) => http.post(`/api/requests/${id}/approve`, body),
  completeRequest: (id, body) => http.post(`/api/requests/${id}/complete`, body),
  cancelRequest: (id, body) => http.post(`/api/requests/${id}/cancel`, body),
  addFollowup: (id, body) => http.post(`/api/requests/${id}/followups`, body),
  completeFollowup: (id, fid) => http.patch(`/api/requests/${id}/followups/${fid}/complete`),
  regenAI: id => http.post(`/api/requests/${id}/regenerate-ai`, null, { timeout: 120000 }),
  getAudit: id => http.get(`/api/requests/${id}/audit`),
  getSimilar: id => http.get(`/api/requests/${id}/similar`),
  streamUrl: id => `${BASE}/api/requests/${id}/stream`,

  // Dashboard
  dashStats: () => http.get('/api/dashboard/stats'),
  dashTrend: days => http.get(`/api/dashboard/trend?days=${days}`),
  byStatus: () => http.get('/api/analytics/by-status'),
  byPriority: () => http.get('/api/analytics/by-priority'),
  byType: () => http.get('/api/analytics/by-type'),
  byChannel: () => http.get('/api/analytics/by-channel'),
  slaStats: () => http.get('/api/analytics/sla'),

  // Agents
  agentStatus: () => http.get('/api/agents/status'),
  codeQuality: body => http.post('/api/agents/code-quality', body, { timeout:200000 }),
  ragSearch: body => http.post('/api/agents/rag/search', body),
  ragStats: () => http.get('/api/agents/rag/stats'),
  getChecklist: () => http.get('/api/agents/checklist'),
  testPipeline: body => http.post('/api/agents/test-pipeline', body),
  gmailSync: body => http.post('/api/ingest/email/sync', body, { timeout: 180000 }),

  // Health
  health: () => http.get('/health'),
}
