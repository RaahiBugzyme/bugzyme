import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../api/client'
import { useAuth } from '../state/AuthContext'

export function AccountAccess({ onSignedIn }: { onSignedIn?: () => void | Promise<void> }) {
  const { user, login, logout, loading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      setPassword('')
      await onSignedIn?.()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not sign in. Check the backend connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="chat-muted" role="status">Checking your Raahi session…</p>
  if (user) return <div className="account-session"><p>Signed in as <strong>{user.full_name || user.username}</strong></p><button type="button" className="matches-outline-button" onClick={logout}>Sign out</button></div>

  return <form className="account-login-form" onSubmit={submit}>
    <label>Email or username<input type="text" autoComplete="username" value={email} onChange={event => setEmail(event.currentTarget.value)} required /></label>
    <label className="login-password-label">Password<span className="login-password-field"><input type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={event => setPassword(event.currentTarget.value)} required /><button type="button" className="login-password-toggle" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? 'Hide' : 'Show'}</button></span></label>
    <div style={{ textAlign: 'right', marginTop: '-2px', marginBottom: '6px' }}>
      <Link to="/forgot-password" style={{ display: 'inline-block', padding: '4px 0', fontSize: '.84rem', color: 'var(--ep)', textDecoration: 'none', fontWeight: 650 }}>Forgot password?</Link>
    </div>
    {error && <p className="chat-error" role="alert">{error}</p>}
    <button type="submit" className="matches-primary-button login-primary-button" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
    <p className="chat-muted">Sign in with your account email. You’ll stay signed in on this device.</p>
  </form>
}
