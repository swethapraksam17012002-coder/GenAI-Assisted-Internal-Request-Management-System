import React, { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { API } from '../utils/api.js'
import { useAuthStore, useUIStore } from '../store/index.js'
import { C, Btn, Alert, Divider, GradientText } from '../components/UI.jsx'

export default function LoginPage() {
  const navigate = useNavigate()
  const { setUser, setToken } = useAuthStore()
  const toast = useUIStore(s => s.addToast)

  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const accessToken = hash.get('access_token')
    const refreshToken = hash.get('refresh_token')

    if (!accessToken || !refreshToken) return

    localStorage.setItem('nexus_access_token', accessToken)
    localStorage.setItem('nexus_refresh_token', refreshToken)
    setToken(accessToken)

    API.me()
      .then(meResp => {
        setUser(meResp.data.data)
        toast('Signed in with Google', 'success')
        window.history.replaceState({}, document.title, '/login')
        navigate('/dashboard')
      })
      .catch(() => {
        localStorage.removeItem('nexus_access_token')
        localStorage.removeItem('nexus_refresh_token')
        setError('Google sign-in completed, but loading your profile failed.')
      })
  }, [navigate, setToken, setUser, toast])

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async e => {
    e.preventDefault()
    setError(''); setSuccess(''); setLoading(true)
    try {
      if (mode === 'login') {
        const { data } = await API.login(form.email, form.password)
        localStorage.setItem('nexus_access_token', data.access_token)
        localStorage.setItem('nexus_refresh_token', data.refresh_token)
        setToken(data.access_token)
        const meResp = await API.me()
        setUser(meResp.data.data)
        toast('Signed in successfully', 'success')
        navigate('/dashboard')
      } else {
        await API.register({
          email: form.email, full_name: form.full_name, password: form.password
        })
        setSuccess('Account created. Your employee ID will be generated automatically.')
        setMode('login')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.error?.message || err.message
      setError(msg)
    } finally { setLoading(false) }
  }

  const field = (label, key, type = 'text', placeholder = '') => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12, color: C.textMid, marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <input type={type} value={form[key]} onChange={set(key)} placeholder={placeholder} required
        style={{ width: '100%', padding: '11px 14px', background: '#0a0f18', border: `1px solid ${C.border}`, borderRadius: 10, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit' }}
        onFocus={e => e.target.style.borderColor = C.primary}
        onBlur={e => e.target.style.borderColor = C.border}
      />
    </div>
  )

  const handleGoogleLogin = () => {
    window.location.href = API.googleLoginUrl()
  }

  return (
    <div style={{ minHeight: '100vh', background: C.bg, display: 'flex', fontFamily: "'DM Sans', 'Segoe UI', sans-serif" }}>
      {/* Left panel — branding */}
      <div style={{
        flex: 1, background: `radial-gradient(ellipse at 30% 50%, #7c6fff14 0%, transparent 70%), ${C.surface}`,
        borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column',
        justifyContent: 'center', padding: '64px 72px',
      }}>
        <div style={{ marginBottom: 64 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: C.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>⚡</div>
            <span style={{ color: C.text, fontWeight: 800, fontSize: 22, letterSpacing: '-0.03em' }}>NEXUS SDLC</span>
          </div>
          <p style={{ color: C.textMid, fontSize: 13 }}>AI-Assisted Request Management</p>
        </div>

        <h1 style={{ color: C.text, fontSize: 40, fontWeight: 800, lineHeight: 1.2, marginBottom: 20, letterSpacing: '-0.03em' }}>
          Every request,<br /><GradientText>AI-processed</GradientText><br />in under 3 seconds.
        </h1>

        <p style={{ color: C.textMid, fontSize: 15, lineHeight: 1.7, maxWidth: 380, marginBottom: 40 }}>
          LangGraph orchestrates 4 CrewAI agents that transform unstructured requests into professional, SLA-tracked documentation automatically.
        </p>

        {[
          ['🤖', 'Multi-Agent AI', 'CrewAI · AutoGen · LangGraph · LangSmith'],
          ['🔐', 'Enterprise Security', 'OAuth2 · JWT · Rate Limiting · RBAC'],
          ['🧠', 'Institutional Memory', 'ChromaDB RAG with semantic search'],
        ].map(([icon, title, sub]) => (
          <div key={title} style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
            <div style={{ fontSize: 20, marginTop: 2 }}>{icon}</div>
            <div>
              <div style={{ color: C.text, fontWeight: 700, fontSize: 14 }}>{title}</div>
              <div style={{ color: C.textMid, fontSize: 12 }}>{sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Right panel — form */}
      <div style={{ width: 440, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48 }}>
        <div style={{ width: '100%' }}>
          {/* Tab switcher */}
          <div style={{ display: 'flex', background: C.surface, borderRadius: 12, padding: 4, marginBottom: 28, border: `1px solid ${C.border}` }}>
            {['login', 'register'].map(m => (
              <button key={m} onClick={() => { setMode(m); setError('') }} style={{
                flex: 1, padding: '9px', border: 'none', borderRadius: 9,
                background: mode === m ? C.card : 'transparent',
                color: mode === m ? C.text : C.textMid,
                fontWeight: 700, fontSize: 13, cursor: 'pointer',
                boxShadow: mode === m ? '0 2px 8px #00000030' : 'none',
                fontFamily: 'inherit',
              }}>{m === 'login' ? 'Sign In' : 'Create Account'}</button>
            ))}
          </div>

          <h2 style={{ color: C.text, fontSize: 24, fontWeight: 800, marginBottom: 6, letterSpacing: '-0.02em' }}>
            {mode === 'login' ? 'Welcome back' : 'Create your account'}
          </h2>
          <p style={{ color: C.textMid, fontSize: 14, marginBottom: 28 }}>
            {mode === 'login' ? 'Sign in to your NEXUS workspace' : 'Get started with AI-powered request management'}
          </p>

          <Alert msg={error} type="error" />
          <Alert msg={success} type="success" />

          <form onSubmit={handleSubmit}>
            {mode === 'register' && field('Full Name', 'full_name', 'text', 'Jane Smith')}
            {field('Email Address', 'email', 'email', 'you@company.com')}
            {field('Password', 'password', 'password', '••••••••••')}

            {mode === 'register' && (
              <div style={{ background: C.primaryLo, border: `1px solid ${C.primary}30`, borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: C.textMid }}>
                Employee IDs are generated automatically. Password must be ≥8 chars with uppercase, digit &amp; special character.
              </div>
            )}

            <Btn type="submit" loading={loading} fullWidth size="lg">
              {mode === 'login' ? '→ Sign In' : '→ Create Account'}
            </Btn>
          </form>

          {mode === 'login' && (
            <div style={{ marginTop: 14 }}>
              <button
                type="button"
                onClick={handleGoogleLogin}
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 10,
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  color: C.text,
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                Continue with Google
              </button>
            </div>
          )}

          <Divider label="secured with" />

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
            {['OAuth2', 'JWT RS256', 'Rate Limiting', 'CSRF', 'RBAC'].map(label => (
              <span key={label} style={{ background: C.accentLo, color: C.accent, border: `1px solid ${C.accent}30`, borderRadius: 6, padding: '3px 9px', fontSize: 11, fontWeight: 700 }}>{label}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
