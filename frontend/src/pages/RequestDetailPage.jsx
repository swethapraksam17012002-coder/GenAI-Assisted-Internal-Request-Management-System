import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { API } from '../utils/api.js'
import { useAuthStore, useUIStore } from '../store/index.js'
import { C, Card, Badge, Btn, Modal, Alert, GradientText, Spinner, Tag, STATUS_C, PRIORITY_C, EmptyState } from '../components/UI.jsx'

const PIPELINE_STEPS = [
  { key: 'Ingest', label: 'Text Ingest', icon: '📥', desc: 'Clean & normalise raw input' },
  { key: 'RequestAnalyzer', label: 'Request Analyzer', icon: '🔍', desc: 'Sentiment, tags, complexity' },
  { key: 'RAGEnrich', label: 'RAG Enrich', icon: '🧠', desc: 'Retrieve similar cases from KB' },
  { key: 'NoteGenerator', label: 'Note Generator', icon: '✍️', desc: 'Produce structured notes' },
  { key: 'QualityGuard', label: 'Quality Guard', icon: '🛡️', desc: 'Score & retry if < 60' },
  { key: 'SLACalculator', label: 'SLA Calculator', icon: '⏱️', desc: 'Compute due date & breach risk' },
]

const AI_PENDING_SUMMARY = 'AI analysis in progress.'

function stepStatusLabel(state) {
  if (state === 'done') return 'completed'
  if (state === 'running') return 'running'
  return 'waiting'
}

function derivePipelineStates(request) {
  if (!request) return {}

  const hasSummary = request.ai_summary && request.ai_summary !== AI_PENDING_SUMMARY
  const hasDetails = request.ai_details && request.ai_details !== 'AI analysis is queued or running for this request.'
  const hasNextAction = request.ai_next_action && request.ai_next_action !== 'Await AI analysis completion and review the generated notes.'
  const hasQuality = request.ai_quality_score != null && request.ai_quality_score > 0
  const hasProcessed = Boolean(request.agent_processing_ms || request.agent_pipeline_run)

  if (!(hasSummary || hasDetails || hasNextAction || hasQuality || hasProcessed)) {
    return {}
  }

  return {
    Ingest: 'done',
    RequestAnalyzer: 'done',
    RAGEnrich: 'done',
    NoteGenerator: hasSummary || hasDetails || hasNextAction ? 'done' : 'waiting',
    QualityGuard: hasQuality || hasProcessed ? 'done' : 'waiting',
    SLACalculator: hasProcessed ? 'done' : 'waiting',
  }
}

export default function RequestDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useUIStore(s => s.addToast)
  const user = useAuthStore(s => s.user)

  const [req, setReq] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('notes')
  const [actionModal, setActionModal] = useState(null) // 'review'|'approve'|'complete'|'cancel'
  const [actionForm, setActionForm] = useState({ performed_by: '', notes: '', reason: '' })
  const [actionLoading, setActionLoading] = useState(false)
  const [followupText, setFollowupText] = useState('')
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesForm, setNotesForm] = useState({})
  const [pipelineStates, setPipelineStates] = useState({})
  const [pipelineActive, setPipelineActive] = useState(false)
  const [pipelineDone, setPipelineDone] = useState(false)
  const streamRef = useRef(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await API.getRequest(id)
      setReq(data.data)
      setNotesForm({ ai_summary: data.data.ai_summary || '', ai_details: data.data.ai_details || '', ai_next_action: data.data.ai_next_action || '' })
      const isRunning = data.data.pipeline_status === 'running'
      setPipelineActive(isRunning)
      if (isRunning) {
        setPipelineDone(false)
      } else {
        setPipelineStates(derivePipelineStates(data.data))
        setPipelineDone(Boolean(data.data.agent_processing_ms || data.data.agent_pipeline_run))
      }
    } catch { toast('Failed to load request', 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [id])

  useEffect(() => {
    if (!req || !pipelineActive) return undefined

    const token = localStorage.getItem('nexus_access_token')
    if (!token) return undefined

    const es = new EventSource(`${API.streamUrl(id)}?token=${token}`)
    streamRef.current = es

    es.addEventListener('agent_started', e => {
      const d = JSON.parse(e.data)
      setPipelineStates(s => ({ ...s, [d.agent]: 'running' }))
      setPipelineDone(false)
    })

    es.addEventListener('agent_completed', e => {
      const d = JSON.parse(e.data)
      setPipelineStates(s => ({ ...s, [d.agent]: 'done' }))
    })

    es.addEventListener('pipeline_done', () => {
      setPipelineActive(false)
      setPipelineDone(true)
      es.close()
      streamRef.current = null
      load()
    })

    es.onerror = () => {
      es.close()
      streamRef.current = null
      setPipelineActive(false)
      load()
    }

    return () => {
      es.close()
      if (streamRef.current === es) streamRef.current = null
    }
  }, [id, req, pipelineActive])

  useEffect(() => () => {
    if (streamRef.current) streamRef.current.close()
  }, [])

  useEffect(() => {
    if (!req || pipelineActive) return
    setPipelineStates(current => {
      const derived = derivePipelineStates(req)
      return Object.keys(derived).length ? derived : current
    })
  }, [req, pipelineActive])

  const isLocked = req && ['Approved','Completed'].includes(req.status)
  const hasPlaceholderNotes = req && (
    req.ai_summary === AI_PENDING_SUMMARY ||
    req.ai_details === 'AI analysis is queued or running for this request.' ||
    req.ai_next_action === 'Await AI analysis completion and review the generated notes.'
  )
  const showAiNotes = req && !pipelineActive && !hasPlaceholderNotes
  const shouldShowPipeline = req && (
    pipelineActive ||
    pipelineDone ||
    req.pipeline_status === 'running' ||
    !req.agent_processing_ms ||
    !req.ai_summary ||
    req.ai_summary === AI_PENDING_SUMMARY
  )

  const doAction = async () => {
    setActionLoading(true)
    try {
      const body = { performed_by: actionForm.performed_by, notes: actionForm.notes, reason: actionForm.reason }
      if (actionModal === 'review')   await API.reviewRequest(id, body)
      if (actionModal === 'approve')  await API.approveRequest(id, body)
      if (actionModal === 'complete') await API.completeRequest(id, body)
      if (actionModal === 'cancel')   await API.cancelRequest(id, body)
      toast(`Request ${actionModal}d`, 'success')
      setActionModal(null)
      load()
    } catch (e) {
      toast(e.response?.data?.error?.message || 'Action failed', 'error')
    } finally { setActionLoading(false) }
  }

  const saveNotes = async () => {
    try {
      await API.updateRequest(id, notesForm)
      toast('Notes saved', 'success')
      setEditingNotes(false)
      load()
    } catch { toast('Save failed', 'error') }
  }

  const addFollowup = async () => {
    if (!followupText.trim()) return
    try {
      const createdBy = user?.full_name || user?.email || 'current_user'
      await API.addFollowup(id, { comment: followupText, created_by: createdBy })
      setFollowupText('')
      toast('Follow-up added', 'success')
      load()
    } catch (e) {
      toast(e.response?.data?.error?.message || e.response?.data?.detail || 'Failed to add follow-up', 'error')
    }
  }

  const regenAI = async () => {
    try {
      setPipelineStates({})
      setPipelineDone(false)
      setPipelineActive(true)
      await API.regenAI(id)
      toast('AI pipeline re-triggered', 'success')
      load()
    } catch { toast('Failed', 'error') }
  }

  if (loading) return <Spinner />
  if (!req) return <div style={{ color: C.danger }}>Request not found</div>

  const tags = (() => { try { return JSON.parse(req.ai_tags || '[]') } catch { return [] } })()

  const TABS = [
    { key: 'notes',    label: '📝 AI Notes' },
    { key: 'followup', label: `💬 Follow-ups (${req.follow_ups?.length || 0})` },
    { key: 'audit',    label: `📜 Audit Trail (${req.audit_logs?.length || 0})` },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 24 }}>
        <Btn variant="ghost" size="sm" onClick={() => navigate('/requests')}>← Back</Btn>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
            <h1 style={{ color: C.primary, fontWeight: 800, fontSize: 22, margin: 0, fontFamily: 'monospace' }}>{req.id}</h1>
            <Badge label={req.status} color={STATUS_C[req.status] || C.textMid} />
            <Badge label={req.priority} color={PRIORITY_C[req.priority] || C.textMid} />
            <Badge label={req.request_type} color={C.textMid} />
            {req.is_overdue && <Badge label="OVERDUE" color={C.danger} />}
          </div>
          <div style={{ color: C.text, fontWeight: 700, fontSize: 15 }}>
            {req.requestor_name} <span style={{ color: C.textDim, fontWeight: 400 }}>({req.requestor_email})</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {req.status === 'Draft' && <Btn variant="ghost" size="sm" onClick={regenAI}>🔄 Regen AI</Btn>}
          {req.status === 'Draft' && <Btn variant="primary" size="sm" onClick={() => setActionModal('review')}>Review</Btn>}
          {req.status === 'Reviewed' && <Btn variant="success" size="sm" onClick={() => setActionModal('approve')}>Approve</Btn>}
          {!['Completed','Cancelled'].includes(req.status) && <Btn variant="ghost" size="sm" onClick={() => setActionModal('complete')}>Complete</Btn>}
          {!['Completed','Cancelled','Approved'].includes(req.status) && <Btn variant="danger" size="sm" onClick={() => setActionModal('cancel')}>Cancel</Btn>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 18 }}>
        {/* Main content */}
        <div>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: `1px solid ${C.border}`, paddingBottom: 0 }}>
            {TABS.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                padding: '10px 16px', border: 'none', borderBottom: `2px solid ${tab === t.key ? C.primary : 'transparent'}`,
                background: 'none', color: tab === t.key ? C.primary : C.textMid, fontWeight: 700,
                fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', transition: 'color .15s',
              }}>{t.label}</button>
            ))}
          </div>

          {tab === 'notes' && (
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 13, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>AI-Generated Notes</div>
                {!isLocked && (
                  <Btn variant="ghost" size="sm" onClick={() => setEditingNotes(!editingNotes)}>
                    {editingNotes ? 'Cancel' : '✏️ Edit'}
                  </Btn>
                )}
              </div>

              {editingNotes ? (
                <>
                  {[['Summary', 'ai_summary', 3], ['Details / Context', 'ai_details', 5], ['Next Action', 'ai_next_action', 3]].map(([label, key, rows]) => (
                    <div key={key} style={{ marginBottom: 16 }}>
                      <label style={{ display: 'block', fontSize: 12, color: C.textMid, marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
                      <textarea value={notesForm[key]} onChange={e => setNotesForm(f => ({ ...f, [key]: e.target.value }))}
                        rows={rows} style={{ width: '100%', padding: '10px 13px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 9, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box', resize: 'vertical', fontFamily: 'inherit' }} />
                    </div>
                  ))}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Btn onClick={saveNotes} variant="success" size="sm">Save Notes</Btn>
                    <Btn onClick={() => setEditingNotes(false)} variant="ghost" size="sm">Cancel</Btn>
                  </div>
                </>
              ) : (
                <>
                  {showAiNotes && [['Summary', req.ai_summary], ['Details / Context', req.ai_details], ['Next Action', req.ai_next_action]].map(([label, val]) => val && (
                    <div key={label} style={{ marginBottom: 20 }}>
                      <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{label}</div>
                      <div style={{ color: C.text, fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{val}</div>
                    </div>
                  ))}
                  {!showAiNotes && (
                    <div style={{ color: C.textDim, fontSize: 13, padding: '20px 0', lineHeight: 1.7 }}>
                      Record created successfully. AI pipeline is running. The notes will appear here automatically after all stages complete.
                    </div>
                  )}
                </>
              )}

              {tags.length > 0 && (
                <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 16, marginTop: 8 }}>
                  <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>AI Tags</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {tags.map(t => <Tag key={t} label={t} />)}
                  </div>
                </div>
              )}
            </Card>
          )}

          {tab === 'followup' && (
            <Card>
              {!isLocked && (
                <div style={{ marginBottom: 20 }}>
                  <textarea value={followupText} onChange={e => setFollowupText(e.target.value)}
                    placeholder="Add a follow-up comment or action…" rows={3}
                    style={{ width: '100%', padding: '10px 13px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 9, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box', resize: 'none', fontFamily: 'inherit', marginBottom: 8 }} />
                  <Btn onClick={addFollowup} size="sm" disabled={!followupText.trim()}>+ Add Follow-up</Btn>
                </div>
              )}
              {req.follow_ups?.length === 0
                ? <EmptyState icon="💬" title="No follow-ups yet" />
                : req.follow_ups?.map(f => (
                  <div key={f.id} style={{ padding: '14px 0', borderBottom: `1px solid ${C.border}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ color: C.text, fontWeight: 700, fontSize: 13 }}>{f.created_by}</span>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {f.is_completed && <Badge label="Done" color={C.success} small />}
                        <span style={{ color: C.textDim, fontSize: 11 }}>{new Date(f.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <div style={{ color: C.textMid, fontSize: 13, lineHeight: 1.6 }}>{f.comment}</div>
                  </div>
                ))
              }
            </Card>
          )}

          {tab === 'audit' && (
            <Card>
              {req.audit_logs?.length === 0
                ? <EmptyState icon="📜" title="No audit events yet" />
                : req.audit_logs?.map(a => (
                  <div key={a.id} style={{ display: 'flex', gap: 14, padding: '12px 0', borderBottom: `1px solid ${C.border}` }}>
                    <div style={{ width: 3, background: C.primary + '60', borderRadius: 2, flexShrink: 0 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ color: C.primary, fontWeight: 700, fontSize: 12 }}>{a.event_type}</span>
                        <span style={{ color: C.textDim, fontSize: 11 }}>{new Date(a.created_at).toLocaleString()}</span>
                      </div>
                      {a.performed_by && <div style={{ color: C.textMid, fontSize: 12 }}>by {a.performed_by}</div>}
                      {a.langsmith_trace_id && <div style={{ color: C.accent, fontSize: 11, marginTop: 4 }}>🔍 Trace: {a.langsmith_trace_id}</div>}
                    </div>
                  </div>
                ))
              }
            </Card>
          )}
        </div>

        {/* Sidebar info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {shouldShowPipeline && (
            <Card style={{ padding: 18 }}>
              <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                🤖 AI Pipeline Progress
              </div>
              {PIPELINE_STEPS.map(step => {
                const state = pipelineStates[step.key]
                const done = state === 'done'
                const running = state === 'running'
                const statusLabel = stepStatusLabel(state)
                return (
                  <div key={step.key} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 12px',
                    borderRadius: 10,
                    marginBottom: 8,
                    background: done ? C.success + '10' : running ? C.primary + '10' : C.surface,
                    border: `1px solid ${done ? C.success + '30' : running ? C.primary + '40' : C.border}`,
                    }}>
                    <div style={{ fontSize: 18, flexShrink: 0 }}>
                      {done ? '✅' : running ? '⚡' : step.icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: done ? C.success : running ? C.primary : C.textMid, fontSize: 13, fontWeight: 700 }}>
                        {step.label}
                      </div>
                      <div style={{ color: C.textDim, fontSize: 11 }}>{`${step.label} ${statusLabel}`}</div>
                      <div style={{ color: C.textDim, fontSize: 11 }}>{step.desc}</div>
                    </div>
                  </div>
                )
              })}
              <div style={{ color: pipelineDone ? C.success : pipelineActive ? C.primary : C.textDim, fontSize: 12, fontWeight: 600, marginTop: 6 }}>
                {pipelineDone ? 'Pipeline complete. AI notes are now available.' : pipelineActive ? 'Record created. AI pipeline running...' : 'Waiting for the next AI run.'}
              </div>
            </Card>
          )}

          <Card style={{ padding: 18 }}>
            <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Request Info</div>
            {[
              ['Type',    req.request_type],
              ['Channel', req.source_channel],
              ['Created', new Date(req.created_at).toLocaleString()],
              ['Due',     req.due_date ? new Date(req.due_date).toLocaleString() : 'Not set'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 13 }}>
                <span style={{ color: C.textMid }}>{k}</span>
                <span style={{ color: C.text, fontWeight: 600, textAlign: 'right', maxWidth: 160 }}>{v}</span>
              </div>
            ))}
          </Card>

          {(req.ai_confidence_score > 0 || req.ai_quality_score != null) && (
            <Card style={{ padding: 18 }}>
              <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>AI Metrics</div>
              {req.ai_confidence_score > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ color: C.textMid, fontSize: 12 }}>Confidence</span>
                    <span style={{ color: req.ai_confidence_score >= 0.7 ? C.success : C.warn, fontWeight: 700, fontSize: 12 }}>{(req.ai_confidence_score * 100).toFixed(0)}%</span>
                  </div>
                  <div style={{ height: 5, background: C.border, borderRadius: 3 }}>
                    <div style={{ height: '100%', width: `${req.ai_confidence_score * 100}%`, background: req.ai_confidence_score >= 0.7 ? C.success : C.warn, borderRadius: 3 }} />
                  </div>
                </div>
              )}
              {req.ai_quality_score != null && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ color: C.textMid, fontSize: 12 }}>Quality Score</span>
                    <span style={{ color: req.ai_quality_score >= 60 ? C.success : C.danger, fontWeight: 700, fontSize: 12 }}>{req.ai_quality_score}/100</span>
                  </div>
                  <div style={{ height: 5, background: C.border, borderRadius: 3 }}>
                    <div style={{ height: '100%', width: `${req.ai_quality_score}%`, background: req.ai_quality_score >= 60 ? C.success : C.danger, borderRadius: 3 }} />
                  </div>
                </div>
              )}
              {req.agent_processing_ms > 0 && (
                <div style={{ color: C.textMid, fontSize: 12 }}>⏱ {req.agent_processing_ms}ms pipeline</div>
              )}
              {req.langsmith_trace_id && (
                <div style={{ color: C.accent, fontSize: 11, marginTop: 6 }}>🔍 LangSmith: {req.langsmith_trace_id}</div>
              )}
            </Card>
          )}

          <Card style={{ padding: 18 }}>
            <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>Raw Description</div>
            <div style={{ color: C.textMid, fontSize: 12, lineHeight: 1.7, maxHeight: 180, overflowY: 'auto' }}>{req.raw_description}</div>
          </Card>
        </div>
      </div>

      {/* Action Modal */}
      <Modal open={!!actionModal} onClose={() => setActionModal(null)}
        title={{ review: 'Review Request', approve: 'Approve Request', complete: 'Complete Request', cancel: 'Cancel Request' }[actionModal]}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: 12, color: C.textMid, marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>Your Name / Email *</label>
          <input value={actionForm.performed_by} onChange={e => setActionForm(f => ({ ...f, performed_by: e.target.value }))}
            placeholder="approver@company.com"
            style={{ width: '100%', padding: '10px 13px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 9, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit' }} />
        </div>
        {actionModal === 'cancel' && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: C.textMid, marginBottom: 6, fontWeight: 600, textTransform: 'uppercase' }}>Reason</label>
            <input value={actionForm.reason} onChange={e => setActionForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="Reason for cancellation…"
              style={{ width: '100%', padding: '10px 13px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: 9, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit' }} />
          </div>
        )}
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn onClick={doAction} loading={actionLoading} disabled={!actionForm.performed_by}
            variant={actionModal === 'cancel' ? 'danger' : actionModal === 'approve' ? 'success' : 'primary'}>
            Confirm
          </Btn>
          <Btn variant="ghost" onClick={() => setActionModal(null)}>Cancel</Btn>
        </div>
      </Modal>
    </div>
  )
}
