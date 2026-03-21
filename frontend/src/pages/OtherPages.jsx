// ── Code Quality Page ─────────────────────────────────────────────────────────
import React, { useState, useEffect } from 'react'
import { API } from '../utils/api.js'
import { C, Card, Btn, Badge, GradientText, Spinner, EmptyState, ProgressBar } from '../components/UI.jsx'

const GRADE_COLOR = { A: '#23d18b', B: '#4caf50', C: '#ffb340', D: '#ff9800', F: '#ff4d6a' }
const AGENT_STATUS_LABELS = {
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

const CODE_QUALITY_STAGES = [
  { key: 'static', label: 'StaticAnalyzer', detail: 'Reviewing security, validation, and performance patterns' },
  { key: 'review', label: 'QualityReviewer', detail: 'Checking maintainability, documentation, and design quality' },
  { key: 'orchestrate', label: 'QualityOrchestrator', detail: 'Combining findings and preparing the final result' },
]

function getAgentStatusMeta(status) {
  const ok = ['ready', 'configured', 'enabled', 'connected'].includes(status)
  const warn = ['fallback_mode', 'disabled', 'litellm_missing', 'llm_not_configured'].includes(status)
  return {
    color: ok ? C.success : warn ? C.warn : C.danger,
    label: AGENT_STATUS_LABELS[status] || status?.replace(/_/g, ' ') || 'Unknown',
  }
}

export function CodeQualityPage() {
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState('python')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progressIndex, setProgressIndex] = useState(0)

  useEffect(() => {
    if (!loading) {
      setProgressIndex(0)
      return
    }

    const timer = window.setInterval(() => {
      setProgressIndex(current => (current < CODE_QUALITY_STAGES.length - 1 ? current + 1 : current))
    }, 2500)

    return () => window.clearInterval(timer)
  }, [loading])

  const run = async () => {
    setError('')
    setResult(null)
    setProgressIndex(0)
    setLoading(true)
    try {
      const { data } = await API.codeQuality({ code, language })
      setResult(data.data)
    } catch (e) {
      setResult(null)
      setError(e.response?.data?.error?.message || (e.code === 'ECONNABORTED' ? 'Analysis request timed out before the backend returned a fallback result.' : 'Analysis failed'))
    }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
          <GradientText>Code Quality Checker</GradientText>
        </h1>
        <p style={{ color: C.textMid, fontSize: 14, marginTop: 6 }}>AutoGen 3-agent group chat: StaticAnalyzer ↔ QualityReviewer ↔ Orchestrator</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <Card style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
              {['python','javascript','typescript','java','go'].map(l => (
                <button key={l} onClick={() => setLanguage(l)} style={{
                  padding: '6px 12px', borderRadius: 7, border: 'none', fontSize: 12, fontWeight: 700,
                  background: language === l ? C.primary : C.surface,
                  color: language === l ? '#fff' : C.textMid, cursor: 'pointer', fontFamily: 'inherit',
                }}>{l}</button>
              ))}
            </div>
            <textarea value={code} onChange={e => setCode(e.target.value)}
              placeholder="# Paste your code here…&#10;# The AutoGen agents will analyse it for:&#10;# Security · Error Handling · Design · Documentation · Performance"
              rows={22} style={{
                width: '100%', padding: '12px 14px',
                background: '#090d14', border: `1px solid ${C.border}`, borderRadius: 10,
                color: '#b8c8e0', fontSize: 13, fontFamily: 'monospace', outline: 'none',
                boxSizing: 'border-box', resize: 'none', lineHeight: 1.6,
              }} />
          </Card>
          {error && <div style={{ color: C.danger, fontSize: 13, marginBottom: 10 }}>✕ {error}</div>}
          <Btn onClick={run} loading={loading} disabled={!code.trim()} fullWidth size="lg">
            🤖 Run AutoGen Analysis
          </Btn>
        </div>

        <div>
          {loading && (
            <Card style={{ padding: '18px 18px 14px', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
                <div>
                  <div style={{ color: C.text, fontSize: 15, fontWeight: 800 }}>Code quality analysis running</div>
                  <div style={{ color: C.textMid, fontSize: 12, marginTop: 4 }}>
                    AutoGen agents are reviewing the submitted code.
                  </div>
                </div>
                <Spinner />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {CODE_QUALITY_STAGES.map((stage, index) => {
                  const status = index < progressIndex ? 'completed' : index === progressIndex ? 'running' : 'waiting'
                  const color = status === 'completed' ? C.success : status === 'running' ? C.primary : C.textDim
                  const statusText = status === 'completed' ? 'completed' : status === 'running' ? 'running' : 'waiting'

                  return (
                    <div key={stage.key} style={{ padding: '10px 12px', borderRadius: 10, border: `1px solid ${color}22`, background: `${color}10` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                        <div style={{ color, fontSize: 13, fontWeight: 700 }}>
                          {stage.label} {statusText}
                        </div>
                        <Badge label={statusText} color={color} small />
                      </div>
                      <div style={{ color: status === 'waiting' ? C.textDim : C.textMid, fontSize: 12, marginTop: 4, lineHeight: 1.5 }}>
                        {stage.detail}
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
          {!loading && !result && (
            <EmptyState icon="🤖" title="AutoGen 3-Agent Analysis" sub="Submit code to run the StaticAnalyzer → QualityReviewer → Orchestrator pipeline" />
          )}
          {result && !loading && (
            <>
              <Card style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                  <div style={{
                    width: 88, height: 88, borderRadius: '50%', flexShrink: 0,
                    background: GRADE_COLOR[result.summary.grade] + '18',
                    border: `3px solid ${GRADE_COLOR[result.summary.grade]}`,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <div style={{ fontSize: 32, fontWeight: 900, color: GRADE_COLOR[result.summary.grade] }}>{result.summary.grade}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 30, fontWeight: 800, color: C.text }}>{result.summary.score}<span style={{ fontSize: 16, color: C.textMid }}>/100</span></div>
                    <div style={{ color: C.textMid, fontSize: 13, marginBottom: 10 }}>{result.summary.recommendation}</div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Badge label={`${result.summary.passed} Pass`} color={C.success} small />
                      <Badge label={`${result.summary.warned} Warn`} color={C.warn} small />
                      <Badge label={`${result.summary.failed} Fail`} color={C.danger} small />
                    </div>
                  </div>
                </div>
              </Card>

              {(result.analysis_message || result.framework_runtime?.message) && (
                <Card style={{ marginBottom: 14, padding: '14px 16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                    <div style={{ color: C.text, fontWeight: 700, fontSize: 13 }}>Analysis Message</div>
                    <Badge
                      label={result.framework_runtime?.status || 'unknown'}
                      color={result.framework_runtime?.autogen_active ? C.success : C.warn}
                      small
                    />
                  </div>
                  {result.analysis_message && (
                    <div style={{ color: C.text, fontSize: 13, lineHeight: 1.6, marginBottom: result.framework_runtime?.message ? 8 : 0 }}>
                      {result.analysis_message}
                    </div>
                  )}
                  {result.framework_runtime?.message && (
                    <div style={{ color: C.textMid, fontSize: 12, lineHeight: 1.6 }}>
                      {result.framework_runtime.message}
                    </div>
                  )}
                </Card>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 520, overflowY: 'auto', paddingRight: 4 }}>
                {result.results?.map(r => (
                  <Card key={r.id} style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ color: C.primary, fontWeight: 800, fontSize: 11, fontFamily: 'monospace' }}>{r.id}</span>
                      <Badge label={r.status}
                        color={r.status === 'PASS' ? C.success : r.status === 'WARN' ? C.warn : C.danger} small />
                    </div>
                    <div style={{ fontSize: 13, color: C.text, marginBottom: r.suggestions?.length ? 6 : 0 }}>{r.observation}</div>
                    {r.suggestions?.[0] && (
                      <div style={{ fontSize: 12, color: C.textMid, display: 'flex', gap: 6 }}>
                        <span>💡</span><span>{r.suggestions[0]}</span>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── RAG Search Page ───────────────────────────────────────────────────────────
export function RAGSearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => { API.ragStats().then(r => setStats(r.data.data)).catch(() => {}) }, [])

  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const { data } = await API.ragSearch({ query, top_k: 5 })
      setResults(data.data.results || [])
    } catch {} finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
          <GradientText>Semantic RAG Search</GradientText>
        </h1>
        <p style={{ color: C.textMid, fontSize: 14, marginTop: 6 }}>Search historical approved requests using natural language · ChromaDB + MiniLM-L6-v2</p>
      </div>

      <Card style={{ marginBottom: 20, padding: '16px 20px' }}>
        <div style={{ display: 'flex', gap: 12 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="e.g. 'production access requests from last month' or 'password reset issues'"
            style={{ flex: 1, padding: '11px 14px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 9, color: C.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' }}
          />
          <Btn onClick={search} loading={loading} disabled={!query.trim()} size="lg">🔍 Search</Btn>
        </div>
        {stats && (
          <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
            {[
              ['Documents', stats.doc_count || 0],
              ['Model', stats.embedding_model || 'N/A'],
              ['Dimensions', stats.embedding_dim || 384],
              ['Status', stats.available ? 'Online' : 'Unavailable'],
            ].map(([k, v]) => (
              <div key={k} style={{ fontSize: 11, color: C.textDim }}>
                <span style={{ fontWeight: 700, color: C.textMid }}>{k}: </span>{v}
              </div>
            ))}
          </div>
        )}
      </Card>

      {loading && <Spinner />}
      {!loading && results.length === 0 && query && (
        <EmptyState icon="🧠" title="No results found" sub="Try different keywords or approve more requests to grow the knowledge base" />
      )}
      {!loading && !query && (
        <EmptyState icon="◈" title="Search the knowledge base" sub="Type a natural language query above and press Enter or click Search" />
      )}
      {!loading && results.map((r, i) => (
        <Card key={i} style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ color: C.primary, fontWeight: 800, fontSize: 13, fontFamily: 'monospace' }}>
              {r.request_id || r.chunk_id}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ height: 6, width: 100, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${r.score * 100}%`, background: C.accent, borderRadius: 3 }} />
              </div>
              <span style={{ color: C.accent, fontSize: 12, fontWeight: 700, minWidth: 36 }}>{(r.score * 100).toFixed(0)}%</span>
            </div>
          </div>
          <div style={{ color: C.textMid, fontSize: 13, lineHeight: 1.6 }}>{r.excerpt}</div>
          {r.metadata && (
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              {r.metadata.request_type && <Badge label={r.metadata.request_type} color={C.textMid} small />}
              {r.metadata.priority && <Badge label={r.metadata.priority} color={C.warn} small />}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

// ── Agents Page ───────────────────────────────────────────────────────────────
export function AgentsPage() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [gmailSyncing, setGmailSyncing] = useState(false)
  const [gmailSyncResult, setGmailSyncResult] = useState(null)
  const [gmailSyncError, setGmailSyncError] = useState('')

  useEffect(() => {
    Promise.all([API.agentStatus(), API.http?.get?.('/api/agents/executions?limit=20').catch(() => ({ data: { data: [] } }))])
      .then(([s]) => setStatus(s.data.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const runGmailSync = async () => {
    setGmailSyncError('')
    setGmailSyncResult(null)
    setGmailSyncing(true)
    try {
      const { data } = await API.gmailSync({ max_messages: 5 })
      setGmailSyncResult(data.data)
    } catch (e) {
      setGmailSyncError(e.response?.data?.detail || e.response?.data?.error?.message || 'Gmail sync failed')
    } finally {
      setGmailSyncing(false)
    }
  }

  if (loading) return <Spinner />

  const FRAMEWORKS = [
    { name: 'LangGraph', icon: '🗺', role: 'Stateful 6-node pipeline graph', agents: ['Ingest', 'Analyse', 'Enrich', 'Generate', 'Quality', 'SLA'] },
    { name: 'CrewAI', icon: '👥', role: '4-agent sequential crew', agents: ['RequestAnalyzer', 'NoteGenerator', 'SLACalculator', 'QualityGuard'] },
    { name: 'AutoGen', icon: '💬', role: '3-agent code quality group chat', agents: ['StaticAnalyzer', 'QualityReviewer', 'QualityOrchestrator'] },
    { name: 'LangSmith', icon: '🔭', role: 'Full pipeline observability', agents: ['Tracer', 'Cost Monitor', 'Eval Suite'] },
  ]

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
          <GradientText>AI Agents</GradientText>
        </h1>
        <p style={{ color: C.textMid, fontSize: 14, marginTop: 6 }}>Multi-framework architecture — LangGraph · CrewAI · AutoGen · LangSmith · RAG</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14, marginBottom: 24 }}>
        {FRAMEWORKS.map(fw => (
          <Card key={fw.name} style={{ padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 28 }}>{fw.icon}</div>
              <div>
                <div style={{ color: C.text, fontWeight: 800, fontSize: 16 }}>{fw.name}</div>
                <div style={{ color: C.textMid, fontSize: 12 }}>{fw.role}</div>
              </div>
              {status?.[fw.name.toLowerCase()] && (
                <Badge label={getAgentStatusMeta(status[fw.name.toLowerCase()]?.status).label}
                  color={getAgentStatusMeta(status[fw.name.toLowerCase()]?.status).color}
                  small
                />
              )}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {fw.agents.map(a => (
                <span key={a} style={{ background: C.primaryLo, color: C.primary, borderRadius: 5, padding: '3px 8px', fontSize: 11, fontWeight: 600 }}>{a}</span>
              ))}
            </div>
          </Card>
        ))}
      </div>

      {status && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>Live Component Health</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            {Object.entries(status).map(([name, info]) => {
              const { color, label } = getAgentStatusMeta(info?.status)
              return (
                <div key={name} style={{ padding: '12px 14px', background: color + '08', border: `1px solid ${color}25`, borderRadius: 10 }}>
                  <div style={{ color: C.text, fontWeight: 700, fontSize: 13, textTransform: 'capitalize', marginBottom: 4 }}>{name}</div>
                  <Badge label={label} color={color} small />
                  {info?.doc_count !== undefined && <div style={{ color: C.textDim, fontSize: 11, marginTop: 4 }}>{info.doc_count} documents</div>}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
          <div>
            <div style={{ color: C.text, fontWeight: 800, fontSize: 16 }}>Gmail Inbox Sync</div>
            <div style={{ color: C.textMid, fontSize: 12, marginTop: 4 }}>
              Pull unread IT mailbox messages into the requests table and run the normal AI pipeline.
            </div>
          </div>
          <Btn onClick={runGmailSync} loading={gmailSyncing} variant="accent">
            Sync Gmail Inbox
          </Btn>
        </div>

        {gmailSyncing && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            {[
              'Connecting to Gmail mailbox',
              'Reading unread email messages',
              'Creating requests and running AI pipeline',
            ].map(step => (
              <div key={step} style={{ padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.primary}22`, background: `${C.primary}10`, color: C.text }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.primary }}>{step} running</div>
              </div>
            ))}
          </div>
        )}

        {gmailSyncError && (
          <div style={{ color: C.danger, fontSize: 13, marginBottom: 8 }}>
            ✕ {gmailSyncError}
          </div>
        )}

        {gmailSyncResult && (
          <div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <Badge label={`Imported ${gmailSyncResult.imported_count || 0}`} color={C.success} small />
              <Badge label={`Skipped ${gmailSyncResult.skipped_count || 0}`} color={C.warn} small />
              <Badge label={`Mailbox ${gmailSyncResult.mailbox || 'unknown'}`} color={C.primary} small />
            </div>

            {gmailSyncResult.imported?.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {gmailSyncResult.imported.map(item => (
                  <div key={item.gmail_message_id} style={{ padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, background: C.surface }}>
                    <div style={{ color: C.text, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                      Imported {item.request_id}
                    </div>
                    <div style={{ color: C.textMid, fontSize: 12, lineHeight: 1.5 }}>
                      {item.requestor_email} · generation {item.frameworks_used?.generation || 'unknown'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: C.textMid, fontSize: 13 }}>
                No new Gmail messages were imported in this sync run.
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Analytics Page ────────────────────────────────────────────────────────────
export function AnalyticsPage() {
  const [sla, setSla] = useState(null)
  const [byType, setByType] = useState({})
  const [byChannel, setByChannel] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([API.slaStats(), API.byType(), API.byChannel()])
      .then(([s, t, c]) => {
        setSla(s.data.data)
        setByType(t.data.data || {})
        setByChannel(c.data.data || {})
      }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
          <GradientText>Analytics</GradientText>
        </h1>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14, marginBottom: 20 }}>
        {sla && [
          ['Total', sla.total, C.primary],
          ['On Time', sla.on_time, C.success],
          ['Overdue', sla.overdue, C.danger],
        ].map(([label, value, color]) => (
          <Card key={label} style={{ textAlign: 'center', padding: 20 }}>
            <div style={{ fontSize: 32, fontWeight: 800, color }}>{value}</div>
            <div style={{ color: C.textMid, fontSize: 12, fontWeight: 600, textTransform: 'uppercase', marginTop: 4 }}>{label}</div>
          </Card>
        ))}
      </div>

      {sla && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>SLA Compliance</div>
          <div style={{ fontSize: 40, fontWeight: 800, color: sla.compliance_rate_pct >= 80 ? C.success : C.warn, marginBottom: 10 }}>
            {sla.compliance_rate_pct}%
          </div>
          <ProgressBar value={sla.compliance_rate_pct} color={sla.compliance_rate_pct >= 80 ? C.success : C.warn} />
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ fontSize: 12, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>By Request Type</div>
          {Object.entries(byType).map(([type, count]) => (
            <div key={type} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ color: C.text, fontSize: 13 }}>{type}</span>
                <span style={{ color: C.primary, fontWeight: 700, fontSize: 13 }}>{count}</span>
              </div>
              <ProgressBar value={count} max={Math.max(...Object.values(byType))} />
            </div>
          ))}
        </Card>

        <Card>
          <div style={{ fontSize: 12, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>By Source Channel</div>
          {Object.entries(byChannel).map(([ch, count]) => (
            <div key={ch} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ color: C.text, fontSize: 13 }}>{ch}</span>
                <span style={{ color: C.accent, fontWeight: 700, fontSize: 13 }}>{count}</span>
              </div>
              <ProgressBar value={count} max={Math.max(...Object.values(byChannel))} color={C.accent} />
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
