import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ApiError } from '../api/client'
import { confirmPasswordResetLink } from '../api/auth'
import { Card } from '../components/Card'
import { PageContainer } from '../components/PageContainer'
import { RaahiWordmark } from '../components/RaahiWordmark'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const email = searchParams.get('email') || ''
  const token = searchParams.get('token') || ''

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  if (!email || !token) {
    return (
      <PageContainer className="matches-page matches-auth-page page-enter">
        <Card className="matches-empty-card matches-auth-card login-auth-card card-enter">
          <div className="login-branding">
            <RaahiWordmark className="login-wordmark" />
            <span>NO GHOSTING. JUST VIBES.</span>
          </div>
          <p className="integration-eyebrow">LINK EXPIRED OR INVALID</p>
          <h1>Reset link missing</h1>
          <p>
            This password reset link is invalid or incomplete. Please request a new recovery link from the Forgot Password page.
          </p>
          <button
            type="button"
            className="matches-primary-button login-primary-button"
            onClick={() => navigate('/forgot-password')}
            style={{ marginTop: '14px' }}
          >
            Go to Forgot Password
          </button>
          <Link className="matches-back-link login-back-link" to="/login">
            Back to Sign in
          </Link>
        </Card>
      </PageContainer>
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setBusy(true)
    try {
      await confirmPasswordResetLink({
        email,
        token,
        new_password: newPassword,
      })
      setSuccess(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Failed to reset password. The link may have expired.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PageContainer className="matches-page matches-auth-page page-enter">
      <Card className="matches-empty-card matches-auth-card login-auth-card card-enter">
        <div className="login-branding">
          <RaahiWordmark className="login-wordmark" />
          <span>NO GHOSTING. JUST VIBES.</span>
        </div>
        <p className="integration-eyebrow">NEW PASSWORD</p>

        {success ? (
          <div style={{ display: 'grid', gap: '14px', textAlign: 'center' }}>
            <h1>Password updated!</h1>
            <p style={{ color: '#8ae2b8' }}>
              Your password has been changed successfully. You can now log in with your new password.
            </p>
            <button
              type="button"
              className="matches-primary-button login-primary-button"
              onClick={() => navigate('/login')}
              style={{ marginTop: '10px' }}
            >
              Sign In Now
            </button>
          </div>
        ) : (
          <form className="account-login-form" onSubmit={handleSubmit}>
            <h1>Set a new password</h1>
            <p className="chat-muted">
              Setting new password for <strong>{email}</strong>
            </p>

            <label>
              New Password
              <div className="login-password-field">
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  value={newPassword}
                  onChange={e => setNewPassword(e.currentTarget.value)}
                  placeholder="At least 8 characters"
                  required
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword(s => !s)}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>

            <label>
              Confirm New Password
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.currentTarget.value)}
                placeholder="Repeat new password"
                required
              />
            </label>

            {error && <p className="chat-error" role="alert">{error}</p>}

            <button
              type="submit"
              className="matches-primary-button login-primary-button"
              disabled={busy}
              style={{ marginTop: '12px' }}
            >
              {busy ? 'Updating password…' : 'Save new password'}
            </button>

            <p className="login-signup-copy" style={{ marginTop: '14px' }}>
              Remembered your password? <Link to="/login">Sign in</Link>
            </p>
          </form>
        )}
      </Card>
    </PageContainer>
  )
}
