import React, { useEffect, useState } from 'react'
import { API } from '../utils/api.js'
import { C, Card, Badge, Spinner, ProgressBar, GradientText, STATUS_C, PRIORITY_C } from '../components/UI.jsx'
const STATUS_LABELS = {
  ready: 'Ready',
  configured: 'Configured',
  enabled: 'Enabled',
  connected: 'Connected',
  fallback_mode: 'Fallback Mode',
  disabled: 'Disabled',
  package_missing: 'Package Missing',
  litellm_missing: 'LiteLLM Missing',
  llm_not_configured: 'LLM Not Configured',
  unknown: 'Unknown',
}

function getAgentStatusMeta(status) {
  const ok = ['ready', 'configured', 'enabled', 'connected'].includes(status)
  const warn = ['fallback_mode', 'disabled', 'litellm_missing', 'llm_not_configured'].includes(status)
  return {
    color: ok ? C.success : warn ? C.warn : C.danger,
    label: STATUS_LABELS[status] || status?.replace(/_/g, ' ') || 'Unknown',
  }
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [trend, setTrend] = useState([])
  const [byStatus, setByStatus] = useState({})
  const [byPriority, setByPriority] = useState({})
  const [agentStatus, setAgentStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      API.dashStats(),
      API.dashTrend(7),
      API.byStatus(),
      API.byPriority(),
      API.agentStatus(),
    ]).then(([s, t, bs, bp, ag]) => {
      setStats(s.data.data)
      setTrend(t.data.data || [])
      setByStatus(bs.data.data || {})
      setByPriority(bp.data.data || {})
      setAgentStatus(ag.data.data || {})
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const kpis = [
    { label: 'Total Requests',   value: stats?.total ?? 0,             icon: '📋', color: C.primary },
    { label: 'Open',             value: stats?.open ?? 0,              icon: '🔵', color: '#4fa3e0' },
    { label: 'Overdue',          value: stats?.overdue ?? 0,           icon: '🔴', color: C.danger },
    { label: 'Completed Today',  value: stats?.completed_today ?? 0,   icon: '✅', color: C.success },
    { label: 'SLA Compliance',   value: `${stats?.sla_compliance_pct ?? 100}%`, icon: '📊', color: C.accent },
    { label: 'Avg Confidence',   value: `${((stats?.avg_confidence ?? 0) * 100).toFixed(0)}%`, icon: '🤖', color: C.primary },
  ]

  const maxTrend = Math.max(...trend.map(t => t.count), 1)

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
          <GradientText>Dashboard</GradientText>
        </h1>
        <p style={{ color: C.textMid, fontSize: 14, marginTop: 6 }}>Real-time overview of your AI-powered request pipeline</p>
      </div>

      {/* KPI grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
        {kpis.map(k => (
          <Card key={k.label} style={{ padding: '20px 22px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 28, fontWeight: 800, color: k.color, letterSpacing: '-0.02em' }}>{k.value}</div>
                <div style={{ fontSize: 12, color: C.textMid, marginTop: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k.label}</div>
              </div>
              <div style={{ fontSize: 22 }}>{k.icon}</div>
            </div>
          </Card>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Trend chart */}
        <Card>
          <div style={{ fontSize: 13, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 20 }}>7-Day Request Trend</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 100 }}>
            {trend.map((t, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                <div style={{ fontSize: 10, color: C.textMid, fontWeight: 700 }}>{t.count}</div>
                <div style={{
                  width: '100%', borderRadius: '5px 5px 0 0',
                  height: `${Math.max(6, (t.count / maxTrend) * 72)}px`,
                  background: `linear-gradient(180deg, ${C.primary} 0%, ${C.primary}88 100%)`,
                  transition: 'height .3s ease',
                }} />
                <div style={{ fontSize: 9, color: C.textDim, fontWeight: 600 }}>{t.date?.slice(5)}</div>
              </div>
            ))}
            {trend.length === 0 && <div style={{ color: C.textDim, fontSize: 13, textAlign: 'center', width: '100%' }}>No data yet</div>}
          </div>
        </Card>

        {/* Status breakdown */}
        <Card>
          <div style={{ fontSize: 13, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 20 }}>By Status</div>
          {Object.entries(byStatus).length === 0
            ? <div style={{ color: C.textDim, fontSize: 13 }}>No data</div>
            : Object.entries(byStatus).map(([status, count]) => (
              <div key={status} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <Badge label={status} color={STATUS_C[status] || C.textMid} small />
                  <span style={{ color: C.text, fontSize: 12, fontWeight: 700 }}>{count}</span>
                </div>
                <ProgressBar value={count} max={stats?.total || 1} color={STATUS_C[status] || C.primary} />
              </div>
            ))
          }
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Priority breakdown */}
        <Card>
          <div style={{ fontSize: 13, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 20 }}>By Priority</div>
          {Object.entries(byPriority).map(([pri, count]) => (
            <div key={pri} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <Badge label={pri} color={PRIORITY_C[pri] || C.textMid} small />
                <span style={{ color: C.text, fontSize: 12, fontWeight: 700 }}>{count}</span>
              </div>
              <ProgressBar value={count} max={stats?.total || 1} color={PRIORITY_C[pri] || C.primary} />
            </div>
          ))}
        </Card>

        {/* AI Agent health */}
        <Card>
          <div style={{ fontSize: 13, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 20 }}>AI Agent Status</div>
          {agentStatus ? Object.entries(agentStatus).map(([name, info]) => {
            const { color, label } = getAgentStatusMeta(info.status)
            return (
              <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, padding: '8px 10px', background: color + '08', borderRadius: 8 }}>
                <span style={{ color: C.text, fontSize: 13, fontWeight: 600, textTransform: 'capitalize' }}>{name}</span>
                <Badge label={label} color={color} small />
              </div>
            )
          }) : <div style={{ color: C.textDim }}>Loading…</div>}
        </Card>
      </div>
    </div>
  )
}
