import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { API } from '../utils/api.js'
import { useUIStore } from '../store/index.js'
import { C, Card, Badge, Btn, Spinner, EmptyState, GradientText, STATUS_C, PRIORITY_C } from '../components/UI.jsx'

export default function RequestsPage() {
  const navigate = useNavigate()
  const toast = useUIStore(s => s.addToast)

  const [requests, setRequests] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ status: '', priority: '', request_type: '', overdue_only: false })
  const [page, setPage] = useState(0)
  const LIMIT = 12

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { skip: page * LIMIT, limit: LIMIT }
      if (search) params.search = search
      if (filters.status) params.status = filters.status
      if (filters.priority) params.priority = filters.priority
      if (filters.request_type) params.request_type = filters.request_type
      if (filters.overdue_only) params.overdue_only = true
      const { data } = await API.listRequests(params)
      setRequests(data.data.requests || [])
      setTotal(data.data.total || 0)
    } catch (e) {
      toast('Failed to load requests', 'error')
    } finally { setLoading(false) }
  }, [page, search, filters])

  useEffect(() => { load() }, [load])

  const fSet = k => v => { setFilters(f => ({ ...f, [k]: v })); setPage(0) }
  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
            <GradientText>Request Register</GradientText>
          </h1>
          <p style={{ color: C.textMid, fontSize: 14, marginTop: 6 }}>{total} total requests</p>
        </div>
        <Btn onClick={() => navigate('/new-request')} variant="accent">+ New Request</Btn>
      </div>

      {/* Filters */}
      <Card style={{ marginBottom: 18, padding: '16px 20px' }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
            placeholder="🔍  Search ID, name, email, summary…"
            style={{
              flex: 2, minWidth: 220, padding: '9px 13px', background: C.surface,
              border: `1px solid ${C.border}`, borderRadius: 8, color: C.text,
              fontSize: 13, outline: 'none', fontFamily: 'inherit',
            }}
          />
          {[
            { key: 'status', opts: ['','Draft','Reviewed','Approved','In Progress','Completed','Overdue','Cancelled'], label: 'Status' },
            { key: 'priority', opts: ['','Critical','High','Medium','Low'], label: 'Priority' },
            { key: 'request_type', opts: ['','Access','Issue','Information','Change','Other'], label: 'Type' },
          ].map(({ key, opts, label }) => (
            <select key={key} value={filters[key]} onChange={e => fSet(key)(e.target.value)}
              style={{ padding: '9px 13px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: filters[key] ? C.text : C.textDim, fontSize: 13, fontFamily: 'inherit' }}>
              <option value="">{label}</option>
              {opts.slice(1).map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ))}
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.textMid, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={filters.overdue_only} onChange={e => fSet('overdue_only')(e.target.checked)} />
            Overdue only
          </label>
          {(search || Object.values(filters).some(Boolean)) && (
            <Btn variant="ghost" size="sm" onClick={() => { setSearch(''); setFilters({ status: '', priority: '', request_type: '', overdue_only: false }); setPage(0) }}>
              × Clear
            </Btn>
          )}
        </div>
      </Card>

      {/* List */}
      {loading ? <Spinner /> : requests.length === 0 ? (
        <EmptyState icon="📭" title="No requests found" sub="Try adjusting your filters or create a new request" />
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {requests.map(req => (
              <Card key={req.id} hover onClick={() => navigate(`/requests/${req.id}`)}
                style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                      <span style={{ color: C.primary, fontWeight: 800, fontSize: 12, fontFamily: 'monospace' }}>{req.id}</span>
                      <Badge label={req.status} color={STATUS_C[req.status] || C.textMid} small />
                      <Badge label={req.priority} color={PRIORITY_C[req.priority] || C.textMid} small />
                      <Badge label={req.request_type} color={C.textMid} small />
                      <Badge label={req.source_channel} color={C.textDim} small />
                      {req.is_overdue && <Badge label="OVERDUE" color={C.danger} small />}
                    </div>
                    <div style={{ color: C.text, fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                      {req.requestor_name}
                      <span style={{ color: C.textDim, fontWeight: 400, fontSize: 12, marginLeft: 8 }}>{req.requestor_email}</span>
                    </div>
                    {req.ai_summary && (
                      <div style={{ color: C.textMid, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 600 }}>
                        🤖 {req.ai_summary}
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ color: C.textDim, fontSize: 12, marginBottom: 6 }}>
                      {new Date(req.created_at).toLocaleDateString()}
                    </div>
                    {req.ai_confidence_score > 0 && (
                      <div style={{ fontSize: 12, color: req.ai_confidence_score >= 0.7 ? C.success : C.warn }}>
                        🤖 {(req.ai_confidence_score * 100).toFixed(0)}%
                      </div>
                    )}
                    {req.ai_quality_score != null && (
                      <div style={{ fontSize: 12, color: req.ai_quality_score >= 60 ? C.success : C.danger, marginTop: 4 }}>
                        Quality {req.ai_quality_score}/100
                      </div>
                    )}
                    {req.due_date && (
                      <div style={{ fontSize: 11, color: req.is_overdue ? C.danger : C.textDim, marginTop: 4 }}>
                        Due {new Date(req.due_date).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 24, alignItems: 'center' }}>
              <Btn variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</Btn>
              <span style={{ color: C.textMid, fontSize: 13 }}>Page {page + 1} / {totalPages}</span>
              <Btn variant="ghost" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>Next →</Btn>
            </div>
          )}
        </>
      )}
    </div>
  )
}
