import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API } from '../utils/api.js'
import { useUIStore } from '../store/index.js'
import { C, Card, Btn, Input, Select, Textarea, Alert, GradientText } from '../components/UI.jsx'

const AGENTS = [
  { key: 'Ingest',           label: 'Text Ingest',        icon: '📥', desc: 'Clean & normalise raw input' },
  { key: 'RequestAnalyzer',  label: 'Request Analyzer',   icon: '🔍', desc: 'Sentiment, tags, complexity' },
  { key: 'RAGEnrich',        label: 'RAG Enrich',         icon: '🧠', desc: 'Retrieve similar cases from KB' },
  { key: 'NoteGenerator',    label: 'Note Generator',     icon: '✍️',  desc: 'Produce structured notes' },
  { key: 'QualityGuard',     label: 'Quality Guard',      icon: '🛡️',  desc: 'Score & retry if < 60' },
  { key: 'SLACalculator',    label: 'SLA Calculator',     icon: '⏱️',  desc: 'Compute due date & breach risk' },
]

function statusLabel(state) {
  if (state === 'done') return 'completed'
  if (state === 'running') return 'running'
  return 'waiting'
}

export default function NewRequestPage() {
  const navigate = useNavigate()
  const toast = useUIStore(s => s.addToast)

  const [form, setForm] = useState({
    requestor_name: '', requestor_email: '', requestor_employee_id: '',
    request_type: 'Access', source_channel: 'Portal',
    priority: 'Medium', raw_description: '',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [draftLoading, setDraftLoading] = useState(false)
  const [error, setError] = useState('')
  const [agentStates, setAgentStates] = useState({}) // key → 'running'|'done'|'retry'
  const [pipelineDone, setPipelineDone] = useState(false)
  const [createdId, setCreatedId] = useState(null)
  const [events, setEvents] = useState([])
  const [createdMessage, setCreatedMessage] = useState('')
  const [draftInfo, setDraftInfo] = useState(null)

  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const addEvent = msg => setEvents(ev => [...ev.slice(-20), msg])

  const validate = () => {
    const e = {}
    if (!form.requestor_name.trim()) e.requestor_name = 'Required'
    if (!form.requestor_email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) e.requestor_email = 'Valid email required'
    if (form.raw_description.length < 10) e.raw_description = 'Minimum 10 characters'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async () => {
    if (!validate()) return
    setError(''); setLoading(true); setAgentStates({}); setPipelineDone(false); setEvents([]); setCreatedMessage('')

    try {
      const { data } = await API.createRequest(form)
      const reqId = data.data.request.id
      setCreatedId(reqId)
      setCreatedMessage(`Record ${reqId} created successfully. AI pipeline is now running.`)
      addEvent(`✅ Request ${reqId} created`)
      toast(`Request ${reqId} created`, 'success')

      // SSE stream
      const token = localStorage.getItem('nexus_access_token')
      const es = new EventSource(`${API.streamUrl(reqId)}?token=${token}`)

      es.addEventListener('agent_started', e => {
        const d = JSON.parse(e.data)
        setAgentStates(s => ({ ...s, [d.agent]: 'running' }))
        addEvent(`🚀 ${d.agent} started`)
      })
      es.addEventListener('agent_completed', e => {
        const d = JSON.parse(e.data)
        setAgentStates(s => ({ ...s, [d.agent]: 'done' }))
        addEvent(`✅ ${d.agent} completed${d.score !== undefined ? ` (score: ${d.score})` : ''}`)
      })
      es.addEventListener('pipeline_done', () => {
        setPipelineDone(true)
        setLoading(false)
        es.close()
        setCreatedMessage(`Record ${reqId} created successfully. AI pipeline completed.`)
        addEvent('🎉 Pipeline complete!')
      })
      es.onerror = () => {
        es.close()
        setLoading(false)
        setPipelineDone(true)
        setCreatedMessage(`Record ${reqId} created successfully. Pipeline stream closed; open the request to verify final AI notes.`)
        addEvent('ℹ️ Stream closed')
      }
    } catch (e) {
      const msg = e.response?.data?.error?.message || e.message
      setError(msg)
      setLoading(false)
    }
  }

  const handleChatFileUpload = async e => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.txt')) {
      setError('Please upload a .txt file for chat or ticket text import.')
      return
    }

    setError('')
    setDraftInfo(null)
    setDraftLoading(true)
    try {
      const text = await file.text()
      const sourceChannel = form.source_channel === 'Ticketing' ? 'Ticketing' : 'Chat'
      const { data } = await API.createDraftFromText({ raw_text: text, source_channel: sourceChannel })
      const draft = data.data
      setForm(current => ({
        ...current,
        requestor_name: draft.requestor_name || current.requestor_name,
        requestor_email: draft.requestor_email || current.requestor_email,
        request_type: draft.request_type || current.request_type,
        priority: draft.priority || current.priority,
        source_channel: draft.source_channel || current.source_channel,
        raw_description: draft.raw_description || current.raw_description,
      }))
      setDraftInfo(draft)
      toast('Text file analysed and form auto-filled', 'success')
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error?.message || 'Unable to analyse uploaded text file')
    } finally {
      setDraftLoading(false)
    }
  }

  const handleFormJsonUpload = async e => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.json')) {
      setError('Please upload a .json file for form import.')
      return
    }

    setError('')
    setDraftInfo(null)
    setDraftLoading(true)
    try {
      const parsed = JSON.parse(await file.text())
      const { data } = await API.createDraftFromFormJson({ json_payload: parsed })
      const draft = data.data
      setForm(current => ({
        ...current,
        requestor_name: draft.requestor_name || current.requestor_name,
        requestor_email: draft.requestor_email || current.requestor_email,
        requestor_employee_id: parsed.requestor_employee_id || current.requestor_employee_id,
        request_type: draft.request_type || current.request_type,
        priority: draft.priority || current.priority,
        source_channel: draft.source_channel || current.source_channel,
        raw_description: draft.raw_description || current.raw_description,
      }))
      setDraftInfo(draft)
      toast('Form JSON analysed and form auto-filled', 'success')
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error?.message || 'Unable to analyse uploaded JSON file')
    } finally {
      setDraftLoading(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <Btn variant="ghost" size="sm" onClick={() => navigate('/requests')}>← Back</Btn>
          <h1 style={{ color: C.text, fontSize: 26, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
            <GradientText>New Request</GradientText>
          </h1>
        </div>
        <p style={{ color: C.textMid, fontSize: 14 }}>AI pipeline will auto-generate structured notes, SLA, and tags.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, alignItems: 'start' }}>
        {/* Form */}
        <Card>
          <Alert msg={error} />

          <Input label="Requestor Name" required value={form.requestor_name}
            onChange={e => set('requestor_name')(e.target.value)} placeholder="Jane Smith"
            error={errors.requestor_name} />

          <Input label="Requestor Email" required type="email" value={form.requestor_email}
            onChange={e => set('requestor_email')(e.target.value)} placeholder="jane@company.com"
            error={errors.requestor_email} />

          <Input label="Employee ID (optional)" value={form.requestor_employee_id}
            onChange={e => set('requestor_employee_id')(e.target.value)} placeholder="EMP-1234" />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Select label="Request Type" required value={form.request_type}
              onChange={e => set('request_type')(e.target.value)}
              options={['Access','Issue','Information','Change','Other']} />
            <Select label="Priority" required value={form.priority}
              onChange={e => set('priority')(e.target.value)}
              options={['Low','Medium','High','Critical']} />
          </div>

          <Select label="Source Channel" required value={form.source_channel}
            onChange={e => set('source_channel')(e.target.value)}
            options={['Portal','Email','Chat','Form','Ticketing']} />

          {(form.source_channel === 'Chat' || form.source_channel === 'Ticketing') && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ color: C.textMid, fontSize: 12, marginBottom: 6, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Upload Chat / Ticket Text
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8, cursor: draftLoading ? 'not-allowed' : 'pointer',
                  padding: '10px 14px', borderRadius: 9, background: C.surface, border: `1px solid ${C.border}`, color: C.text,
                  opacity: draftLoading ? 0.7 : 1,
                }}>
                  <input type="file" accept=".txt,text/plain" onChange={handleChatFileUpload} disabled={draftLoading} style={{ display: 'none' }} />
                  <span>{draftLoading ? 'Analysing text file...' : 'Upload .txt file'}</span>
                </label>
                <div style={{ color: C.textDim, fontSize: 12 }}>
                  Upload a chat transcript or ticket export to auto-fill the form.
                </div>
              </div>
              {draftInfo && (
                <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.primary}25`, background: C.primaryLo }}>
                  <div style={{ color: C.text, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                    Draft prefill ready
                  </div>
                  <div style={{ color: C.textMid, fontSize: 12, lineHeight: 1.6 }}>
                    Suggested summary: {draftInfo.ai_summary_preview || 'N/A'}
                  </div>
                  {draftInfo.ai_tags_preview?.length > 0 && (
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                      {draftInfo.ai_tags_preview.map(tag => (
                        <span key={tag} style={{ background: C.primary + '18', color: C.primary, borderRadius: 5, padding: '2px 7px', fontSize: 11, fontWeight: 600 }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {form.source_channel === 'Form' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ color: C.textMid, fontSize: 12, marginBottom: 6, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Upload Form JSON
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8, cursor: draftLoading ? 'not-allowed' : 'pointer',
                  padding: '10px 14px', borderRadius: 9, background: C.surface, border: `1px solid ${C.border}`, color: C.text,
                  opacity: draftLoading ? 0.7 : 1,
                }}>
                  <input type="file" accept=".json,application/json" onChange={handleFormJsonUpload} disabled={draftLoading} style={{ display: 'none' }} />
                  <span>{draftLoading ? 'Analysing JSON file...' : 'Upload .json file'}</span>
                </label>
                <div style={{ color: C.textDim, fontSize: 12 }}>
                  Upload a structured form payload to auto-fill the request before submission.
                </div>
              </div>
              {draftInfo && (
                <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.primary}25`, background: C.primaryLo }}>
                  <div style={{ color: C.text, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                    Draft prefill ready
                  </div>
                  <div style={{ color: C.textMid, fontSize: 12, lineHeight: 1.6 }}>
                    Suggested summary: {draftInfo.ai_summary_preview || 'N/A'}
                  </div>
                  {draftInfo.ai_tags_preview?.length > 0 && (
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                      {draftInfo.ai_tags_preview.map(tag => (
                        <span key={tag} style={{ background: C.primary + '18', color: C.primary, borderRadius: 5, padding: '2px 7px', fontSize: 11, fontWeight: 600 }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <Textarea label="Description" required rows={7}
            value={form.raw_description}
            onChange={e => set('raw_description')(e.target.value)}
            placeholder="Describe the request in detail. The more context you provide, the better the AI-generated notes will be. (min 10 characters)"
            error={errors.raw_description} />

          <div style={{ display: 'flex', gap: 10 }}>
            <Btn onClick={handleSubmit} disabled={loading || pipelineDone} size="lg" fullWidth>
              {pipelineDone ? '✅ Pipeline Complete' : loading ? 'Submit complete. Pipeline running...' : '🚀 Submit & Run AI Pipeline'}
            </Btn>
            {pipelineDone && createdId && (
              <Btn onClick={() => navigate(`/requests/${createdId}`)} variant="accent" size="lg">
                View Request →
              </Btn>
            )}
          </div>
          {createdMessage && (
            <div style={{ marginTop: 12, color: pipelineDone ? C.success : C.primary, fontSize: 13, fontWeight: 600 }}>
              {createdMessage}
            </div>
          )}
        </Card>

        {/* Pipeline progress */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card style={{ padding: 20 }}>
            <div style={{ fontSize: 12, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>
              🤖 AI Pipeline Progress
            </div>

            {AGENTS.map(agent => {
              const state = agentStates[agent.key]
              const done = state === 'done'
              const running = state === 'running'
              const currentStatus = statusLabel(state)
              return (
                <div key={agent.key} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 12px', borderRadius: 10, marginBottom: 8,
                  background: done ? C.success + '10' : running ? C.primary + '10' : C.surface,
                  border: `1px solid ${done ? C.success + '30' : running ? C.primary + '40' : C.border}`,
                  transition: 'all .3s ease',
                }}>
                  <div style={{ fontSize: 18, flexShrink: 0 }}>
                    {done ? '✅' : running ? '⚡' : agent.icon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: done ? C.success : running ? C.primary : C.textMid, fontSize: 13, fontWeight: 700 }}>
                      {agent.label}
                    </div>
                    <div style={{ color: C.textDim, fontSize: 11 }}>{`${agent.label} ${currentStatus}`}</div>
                    <div style={{ color: C.textDim, fontSize: 11 }}>{agent.desc}</div>
                  </div>
                </div>
              )
            })}

            {pipelineDone && (
              <div style={{ textAlign: 'center', padding: '12px 0 4px', color: C.success, fontWeight: 700, fontSize: 13 }}>
                🎉 All agents completed!
              </div>
            )}
          </Card>

          {events.length > 0 && (
            <Card style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Event Log</div>
              <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                {events.map((e, i) => (
                  <div key={i} style={{ color: C.textDim, fontSize: 11, marginBottom: 3, fontFamily: 'monospace' }}>{e}</div>
                ))}
              </div>
            </Card>
          )}

          <Card style={{ padding: 16 }}>
            <div style={{ fontSize: 11, color: C.textMid, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>SLA Preview</div>
            {form.priority && form.request_type && (() => {
              const matrix = { Critical: { Access: 2, Issue: 1, Information: 4, Change: 8, Other: 4 }, High: { Access: 8, Issue: 4, Information: 8, Change: 24, Other: 8 }, Medium: { Access: 24, Issue: 16, Information: 24, Change: 48, Other: 24 }, Low: { Access: 48, Issue: 32, Information: 48, Change: 96, Other: 48 } }
              const hrs = matrix[form.priority]?.[form.request_type] || 24
              const due = new Date(Date.now() + hrs * 3600000)
              return (
                <div>
                  <div style={{ color: C.text, fontWeight: 700, fontSize: 20 }}>{hrs}h</div>
                  <div style={{ color: C.textMid, fontSize: 12 }}>Due: {due.toLocaleString()}</div>
                </div>
              )
            })()}
          </Card>
        </div>
      </div>
    </div>
  )
}
