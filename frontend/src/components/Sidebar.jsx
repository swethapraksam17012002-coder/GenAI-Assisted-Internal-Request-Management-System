import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from '../store/index.js'
import { API } from '../utils/api.js'
import { C, Badge, GradientText } from './UI.jsx'

const NAV = [
  { to: '/dashboard',    icon: '▤',  label: 'Dashboard' },
  { to: '/requests',     icon: '☰',  label: 'Requests' },
  { to: '/new-request',  icon: '+',  label: 'New Request', accent: true },
  { to: '/code-quality', icon: '⌥',  label: 'Code Quality' },
  { to: '/rag-search',   icon: '◈',  label: 'RAG Search' },
  { to: '/agents',       icon: '⬡',  label: 'AI Agents' },
  { to: '/analytics',    icon: '≡',  label: 'Analytics' },
]

export default function Sidebar() {
  const { user, logout } = useAuthStore()
  const { sidebarCollapsed, toggleSidebar, addToast } = useUIStore()
  const navigate = useNavigate()
  const collapsed = sidebarCollapsed

  const handleLogout = async () => {
    try { await API.logout() } catch {}
    logout()
    addToast('Signed out', 'success')
    navigate('/login')
  }

  return (
    <aside style={{
      width: collapsed ? 64 : 220,
      minHeight: '100vh',
      background: C.surface,
      borderRight: `1px solid ${C.border}`,
      display: 'flex', flexDirection: 'column',
      transition: 'width .2s ease',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: collapsed ? '20px 0' : '22px 20px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: `1px solid ${C.border}`, justifyContent: collapsed ? 'center' : 'flex-start' }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: C.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>⚡</div>
        {!collapsed && (
          <div>
            <div style={{ color: C.text, fontWeight: 800, fontSize: 15, letterSpacing: '-0.02em' }}>NEXUS</div>
            <div style={{ color: C.textDim, fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>SDLC</div>
          </div>
        )}
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1, padding: '12px 8px' }}>
        {NAV.map(item => (
          <NavLink key={item.to} to={item.to} style={({ isActive }) => ({
            display: 'flex', alignItems: 'center', gap: 10,
            padding: collapsed ? '10px 0' : '10px 12px',
            borderRadius: 10, marginBottom: 2,
            textDecoration: 'none',
            justifyContent: collapsed ? 'center' : 'flex-start',
            background: isActive ? (item.accent ? C.accentLo : C.primaryLo) : 'transparent',
            borderLeft: isActive ? `3px solid ${item.accent ? C.accent : C.primary}` : '3px solid transparent',
            color: isActive ? (item.accent ? C.accent : C.primary) : C.textMid,
            fontWeight: isActive ? 700 : 500,
            fontSize: 14,
            transition: 'all .15s',
          })}>
            <span style={{ fontSize: 16, flexShrink: 0, fontStyle: 'normal' }}>{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
            {!collapsed && item.accent && (
              <span style={{ marginLeft: 'auto', background: C.accent, color: '#080b12', borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 800 }}>NEW</span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User profile */}
      <div style={{ padding: collapsed ? '12px 8px' : '12px 14px', borderTop: `1px solid ${C.border}` }}>
        {!collapsed && user && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ color: C.text, fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{user.full_name}</div>
            <div style={{ color: C.textDim, fontSize: 11, marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {user.scopes?.slice(0, 3).map(s => <Badge key={s} label={s} color={C.primary} small />)}
            </div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, justifyContent: collapsed ? 'center' : 'flex-start' }}>
          <button onClick={toggleSidebar} title="Toggle sidebar" style={{
            background: 'none', border: `1px solid ${C.border}`, borderRadius: 7,
            color: C.textMid, cursor: 'pointer', padding: '6px 9px', fontSize: 12,
          }}>{collapsed ? '→' : '←'}</button>
          {!collapsed && (
            <button onClick={handleLogout} style={{
              flex: 1, background: 'none', border: `1px solid ${C.border}`, borderRadius: 7,
              color: C.textMid, cursor: 'pointer', padding: '6px 9px', fontSize: 12, fontWeight: 600,
            }}>Sign Out</button>
          )}
        </div>
      </div>
    </aside>
  )
}
