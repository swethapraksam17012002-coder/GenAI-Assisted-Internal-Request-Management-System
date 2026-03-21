import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { API } from './utils/api.js'
import { useAuthStore, useUIStore } from './store/index.js'
import { C, Spinner, ToastContainer } from './components/UI.jsx'
import Sidebar from './components/Sidebar.jsx'

import LoginPage       from './pages/LoginPage.jsx'
import DashboardPage   from './pages/DashboardPage.jsx'
import RequestsPage    from './pages/RequestsPage.jsx'
import NewRequestPage  from './pages/NewRequestPage.jsx'
import RequestDetailPage from './pages/RequestDetailPage.jsx'
import { CodeQualityPage, RAGSearchPage, AgentsPage, AnalyticsPage } from './pages/OtherPages.jsx'

// ── Auth guard layout ────────────────────────────────────────────────────────
function ProtectedLayout() {
  const { user, token, setUser, setLoading, loading } = useAuthStore()
  const { sidebarCollapsed, toasts, removeToast } = useUIStore()

  useEffect(() => {
    if (token && !user) {
      API.me()
        .then(r => setUser(r.data.data))
        .catch(() => {
          localStorage.removeItem('nexus_access_token')
          localStorage.removeItem('nexus_refresh_token')
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [token])

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>⚡</div>
          <Spinner />
          <div style={{ color: C.textMid, fontSize: 14, marginTop: 8 }}>Starting NEXUS…</div>
        </div>
      </div>
    )
  }

  if (!token || !user) return <Navigate to="/login" replace />

  return (
    <div style={{
      display: 'flex', minHeight: '100vh', background: C.bg,
      fontFamily: "'DM Sans', 'Segoe UI', -apple-system, sans-serif",
      color: C.text,
    }}>
      <Sidebar />
      <main style={{
        flex: 1, padding: '32px 36px',
        overflowY: 'auto',
        minWidth: 0,
        background: `radial-gradient(ellipse at 80% 0%, #7c6fff08 0%, transparent 50%)`,
      }}>
        <Outlet />
      </main>
      <ToastContainer toasts={toasts} remove={removeToast} />
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"    element={<DashboardPage />} />
          <Route path="/requests"     element={<RequestsPage />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route path="/new-request"  element={<NewRequestPage />} />
          <Route path="/code-quality" element={<CodeQualityPage />} />
          <Route path="/rag-search"   element={<RAGSearchPage />} />
          <Route path="/agents"       element={<AgentsPage />} />
          <Route path="/analytics"    element={<AnalyticsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>

      {/* Global font */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
        *, *::before, *::after { box-sizing: border-box; }
        body { margin: 0; background: ${C.bg}; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: ${C.surface}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: ${C.borderHi}; }
        a { color: inherit; text-decoration: none; }
        button, select, input, textarea { font-family: inherit; }
      `}</style>
    </BrowserRouter>
  )
}
