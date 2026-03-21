// Shared UI components for NEXUS SDLC
// Aesthetic: industrial dark — ink-black base, electric violet accent, amber warnings

export const C = {
  bg:        '#080b12',
  surface:   '#0e1219',
  card:      '#111620',
  border:    '#1e2535',
  borderHi:  '#2d3a52',
  primary:   '#7c6fff',
  primaryLo: '#7c6fff18',
  accent:    '#00e5c3',
  accentLo:  '#00e5c312',
  warn:      '#ffb340',
  danger:    '#ff4d6a',
  success:   '#23d18b',
  text:      '#dde3f0',
  textMid:   '#8b96b0',
  textDim:   '#4a5568',
  grad:      'linear-gradient(135deg, #7c6fff 0%, #00e5c3 100%)',
}

export const STATUS_C = {
  Draft: '#8b96b0', Reviewed: '#4fa3e0', Approved: '#23d18b',
  'In Progress': '#7c6fff', Completed: '#23d18b', Overdue: '#ff4d6a', Cancelled: '#4a5568'
}
export const PRIORITY_C = {
  Critical: '#ff4d6a', High: '#ffb340', Medium: '#7c6fff', Low: '#23d18b'
}

export function Badge({ label, color, small }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      background: color + '18', color, border: `1px solid ${color}35`,
      borderRadius: 5, padding: small ? '1px 6px' : '3px 9px',
      fontSize: small ? 10 : 11, fontWeight: 700, letterSpacing: '0.04em',
      textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>{label}</span>
  )
}

export function Card({ children, style, hover, onClick }) {
  return (
    <div onClick={onClick} style={{
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: 14, padding: 22,
      transition: 'border-color .15s, box-shadow .15s',
      cursor: onClick ? 'pointer' : 'default',
      ...style,
    }}
    onMouseEnter={hover ? e => {
      e.currentTarget.style.borderColor = C.borderHi
      e.currentTarget.style.boxShadow = `0 4px 24px ${C.primary}14`
    } : undefined}
    onMouseLeave={hover ? e => {
      e.currentTarget.style.borderColor = C.border
      e.currentTarget.style.boxShadow = 'none'
    } : undefined}
    >{children}</div>
  )
}

export function Btn({ children, onClick, variant = 'primary', disabled, loading, size = 'md', fullWidth, type = 'button' }) {
  const pad = size === 'sm' ? '7px 14px' : size === 'lg' ? '13px 28px' : '10px 20px'
  const fs  = size === 'sm' ? 12 : size === 'lg' ? 15 : 13
  const variants = {
    primary: { background: C.primary, color: '#fff', border: 'none' },
    accent:  { background: C.accent,  color: '#080b12', border: 'none' },
    ghost:   { background: 'transparent', color: C.textMid, border: `1px solid ${C.border}` },
    danger:  { background: C.danger,  color: '#fff', border: 'none' },
    success: { background: C.success, color: '#080b12', border: 'none' },
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled || loading} style={{
      ...variants[variant], borderRadius: 9, padding: pad, fontSize: fs, fontWeight: 700,
      cursor: disabled || loading ? 'not-allowed' : 'pointer',
      opacity: disabled || loading ? 0.55 : 1,
      transition: 'opacity .15s, filter .15s',
      width: fullWidth ? '100%' : undefined,
      fontFamily: 'inherit',
    }}
    onMouseEnter={e => { if (!disabled && !loading) e.currentTarget.style.filter = 'brightness(1.12)' }}
    onMouseLeave={e => { e.currentTarget.style.filter = 'none' }}
    >{loading ? '⏳ …' : children}</button>
  )
}

export function Field({ label, required, children, error }) {
  return (
    <div style={{ marginBottom: 16 }}>
      {label && (
        <label style={{ display: 'block', fontSize: 12, color: C.textMid, marginBottom: 6, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          {label}{required && <span style={{ color: C.danger }}> *</span>}
        </label>
      )}
      {children}
      {error && <div style={{ color: C.danger, fontSize: 12, marginTop: 4 }}>{error}</div>}
    </div>
  )
}

export function Input({ label, required, error, ...props }) {
  return (
    <Field label={label} required={required} error={error}>
      <input {...props} style={{
        width: '100%', padding: '10px 13px', background: C.surface,
        border: `1px solid ${error ? C.danger : C.border}`, borderRadius: 9,
        color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box',
        fontFamily: 'inherit', transition: 'border-color .15s',
        ...(props.style || {}),
      }}
      onFocus={e => e.target.style.borderColor = C.primary}
      onBlur={e => e.target.style.borderColor = error ? C.danger : C.border}
      />
    </Field>
  )
}

export function Textarea({ label, required, error, rows = 5, ...props }) {
  return (
    <Field label={label} required={required} error={error}>
      <textarea {...props} rows={rows} style={{
        width: '100%', padding: '10px 13px', background: C.surface,
        border: `1px solid ${error ? C.danger : C.border}`, borderRadius: 9,
        color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box',
        fontFamily: 'inherit', resize: 'vertical', lineHeight: 1.5,
        ...(props.style || {}),
      }}
      onFocus={e => e.target.style.borderColor = C.primary}
      onBlur={e => e.target.style.borderColor = error ? C.danger : C.border}
      />
    </Field>
  )
}

export function Select({ label, required, error, options, ...props }) {
  return (
    <Field label={label} required={required} error={error}>
      <select {...props} style={{
        width: '100%', padding: '10px 13px', background: C.surface,
        border: `1px solid ${error ? C.danger : C.border}`, borderRadius: 9,
        color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box',
        fontFamily: 'inherit',
        ...(props.style || {}),
      }}>
        {options.map(o => (
          typeof o === 'string'
            ? <option key={o} value={o}>{o || '— All —'}</option>
            : <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </Field>
  )
}

export function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48 }}>
      <div style={{
        width: 36, height: 36, border: `3px solid ${C.border}`,
        borderTopColor: C.primary, borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

export function Alert({ msg, type = 'error' }) {
  if (!msg) return null
  const color = type === 'error' ? C.danger : type === 'warn' ? C.warn : C.success
  return (
    <div style={{
      padding: '12px 16px', borderRadius: 9, marginBottom: 16,
      background: color + '18', color, border: `1px solid ${color}35`, fontSize: 13,
    }}>{msg}</div>
  )
}

export function Divider({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
      <div style={{ flex: 1, height: 1, background: C.border }} />
      {label && <span style={{ color: C.textDim, fontSize: 12 }}>{label}</span>}
      <div style={{ flex: 1, height: 1, background: C.border }} />
    </div>
  )
}

export function Tag({ label }) {
  return (
    <span style={{
      background: C.primaryLo, color: C.primary, borderRadius: 5,
      padding: '2px 7px', fontSize: 11, fontWeight: 600,
    }}>{label}</span>
  )
}

export function GradientText({ children }) {
  return (
    <span style={{
      background: C.grad, WebkitBackgroundClip: 'text',
      WebkitTextFillColor: 'transparent', backgroundClip: 'text',
    }}>{children}</span>
  )
}

export function EmptyState({ icon, title, sub }) {
  return (
    <div style={{ textAlign: 'center', padding: '56px 24px' }}>
      <div style={{ fontSize: 48, marginBottom: 12 }}>{icon}</div>
      <div style={{ color: C.text, fontWeight: 700, fontSize: 17, marginBottom: 6 }}>{title}</div>
      {sub && <div style={{ color: C.textMid, fontSize: 14 }}>{sub}</div>}
    </div>
  )
}

export function ProgressBar({ value, max = 100, color }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ height: 6, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
      <div style={{
        height: '100%', width: `${pct}%`, borderRadius: 3,
        background: color || C.primary, transition: 'width .4s ease',
      }} />
    </div>
  )
}

export function Modal({ open, onClose, title, children, width = 540 }) {
  if (!open) return null
  return (
    <div style={{
      position: 'fixed', inset: 0, background: '#00000088', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: C.card, border: `1px solid ${C.borderHi}`,
        borderRadius: 16, width: '100%', maxWidth: width,
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: `0 24px 80px #00000060`,
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '20px 24px', borderBottom: `1px solid ${C.border}`,
        }}>
          <h3 style={{ margin: 0, color: C.text, fontSize: 17, fontWeight: 700 }}>{title}</h3>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: C.textMid,
            cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 4,
          }}>×</button>
        </div>
        <div style={{ padding: 24 }}>{children}</div>
      </div>
    </div>
  )
}

export function ToastContainer({ toasts, remove }) {
  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {toasts.map(t => (
        <div key={t.id} onClick={() => remove(t.id)} style={{
          padding: '12px 18px', borderRadius: 10, cursor: 'pointer',
          background: t.type === 'error' ? C.danger : t.type === 'warn' ? C.warn : C.success,
          color: t.type === 'warn' ? '#0a0a14' : '#fff',
          fontSize: 13, fontWeight: 600, boxShadow: '0 4px 20px #00000040',
          maxWidth: 340, animation: 'slideUp .2s ease',
        }}>
          {t.type === 'error' ? '✕ ' : t.type === 'warn' ? '⚠ ' : '✓ '}{t.msg}
        </div>
      ))}
      <style>{`@keyframes slideUp { from { opacity:0; transform: translateY(8px) } to { opacity:1; transform: translateY(0) } }`}</style>
    </div>
  )
}
