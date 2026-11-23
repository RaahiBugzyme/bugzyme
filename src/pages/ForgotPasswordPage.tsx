import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { sendPasswordResetOtp, verifyPasswordResetOtp, sendPasswordResetLink } from '../api/auth'
import { Card } from '../components/Card'
import { PageContainer } from '../components/PageContainer'
import { RaahiWordmark } from '../components/RaahiWordmark'

type RecoveryStage = 'input-email' | 'otp-verify' | 'link-sent' | 'reset-success'
type ChosenMethod = 'otp' | 'link'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [chosenMethod, setChosenMethod] = useState<ChosenMethod>('otp')
  const [stage, setStage] = useState<RecoveryStage>('input-email')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')

  // OTP Form fields
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [resendCountdown, setResendCountdown] = useState(0)

  useEffect(() => {
    if (resendCountdown <= 0) return
    const timer = setInterval(() => setResendCountdown(c => c - 1), 1000)
    return () => clearInterval(timer)
  }, [resendCountdown])

  async function handleSendRecovery(method: ChosenMethod) {
    setError('')
    setInfoMessage('')
    const trimmedEmail = email.trim()
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError('Please enter a valid email address.')
      return
    }

    setBusy(true)
    try {
      if (method === 'otp') {
        const res = await sendPasswordResetOtp(trimmedEmail)
        setStage('otp-verify')
        setResendCountdown(60)
        setInfoMessage(res.message || 'If an account exists, a 6-digit code has been sent.')
      } else {
        const res = await sendPasswordResetLink(trimmedEmail)
        setStage('link-sent')
        setResendCountdown(60)
        setInfoMessage(res.message || 'If an account exists, a reset link has been sent.')
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not process request. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function handleVerifyOtp(event: FormEvent) {
    event.preventDefault()
    setError('')
    const trimmedOtp = otp.trim()
    if (!/^\d{6}$/.test(trimmedOtp)) {
      setError('Please enter the 6-digit verification code.')
      return
    }
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
      await verifyPasswordResetOtp({
        email: email.trim(),
        otp: trimmedOtp,
        new_password: newPassword,
      })
      setStage('reset-success')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Verification failed. Check the code and try again.')
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
        <p className="integration-eyebrow">ACCOUNT RECOVERY</p>

        {stage === 'input-email' && (
          <>
            <h1>Forgot your password?</h1>
            <p>Enter your email and choose how you would like to recover your account.</p>

            <div className="account-login-form">
              <label>
                Email address
                <input
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  maxLength={254}
                  value={email}
                  onChange={e => setEmail(e.currentTarget.value)}
                  required
                />
              </label>

              <div style={{ marginTop: '10px' }}>
                <p style={{ fontSize: '.84rem', fontWeight: 750, margin: '0 0 10px', color: 'rgba(255,255,255,.9)' }}>
                  Choose recovery method:
                </p>
                <div style={{ display: 'grid', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => setChosenMethod('otp')}
                    className={`recovery-method-option${chosenMethod === 'otp' ? ' selected' : ''}`}
                  >
                    <span style={{ fontWeight: 800, fontSize: '.9rem', color: chosenMethod === 'otp' ? '#f28ac7' : '#fff' }}>
                      ✉️ 6-Digit Email Code (Instant)
                    </span>
                    <span style={{ fontSize: '.78rem', color: 'rgba(255,255,255,.7)', marginTop: '3px' }}>
                      Receive a one-time verification code in your email to reset your password immediately on this screen.
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setChosenMethod('link')}
                    className={`recovery-method-option${chosenMethod === 'link' ? ' selected' : ''}`}
                  >
                    <span style={{ fontWeight: 800, fontSize: '.9rem', color: chosenMethod === 'link' ? '#f28ac7' : '#fff' }}>
                      🔗 Password Reset Link
                    </span>
                    <span style={{ fontSize: '.78rem', color: 'rgba(255,255,255,.7)', marginTop: '3px' }}>
                      Receive a secure, clickable link sent to your email to open a dedicated password reset page.
                    </span>
                  </button>
                </div>
              </div>

              {error && <p className="chat-error" role="alert">{error}</p>}

              <button
                type="button"
                className="matches-primary-button login-primary-button"
                disabled={busy}
                onClick={() => void handleSendRecovery(chosenMethod)}
                style={{ marginTop: '12px' }}
              >
                {busy ? 'Sending request…' : chosenMethod === 'otp' ? 'Send 6-digit code' : 'Send password reset link'}
              </button>
            </div>
          </>
        )}

        {stage === 'otp-verify' && (
          <form className="account-login-form" onSubmit={handleVerifyOtp}>
            <h1>Enter verification code</h1>
            <p className="chat-muted" style={{ margin: '0 0 12px' }}>
              We sent a 6-digit code to <strong>{email}</strong>.{' '}
              <button
                type="button"
                className="chat-link"
                style={{ background: 'none', border: 'none', color: '#f28ac7', cursor: 'pointer', padding: 0 }}
                onClick={() => { setStage('input-email'); setError('') }}
              >
                Change email
              </button>
            </p>

            {infoMessage && <p className="chat-muted" style={{ color: '#8ae2b8' }}>{infoMessage}</p>}

            <label>
              6-Digit Code
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                placeholder="123456"
                value={otp}
                onChange={e => setOtp(e.currentTarget.value)}
                required
              />
            </label>

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

            <button type="submit" className="matches-primary-button login-primary-button" disabled={busy}>
              {busy ? 'Resetting password…' : 'Reset password'}
            </button>

            <div className="auth-action-row">
              <button
                type="button"
                className="matches-outline-button"
                disabled={resendCountdown > 0 || busy}
                onClick={() => void handleSendRecovery('otp')}
                style={{ fontSize: '.84rem' }}
              >
                {resendCountdown > 0 ? `Resend code (${resendCountdown}s)` : 'Resend code'}
              </button>
              <button
                type="button"
                className="chat-link"
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,.7)', cursor: 'pointer', fontSize: '.84rem' }}
                onClick={() => { setStage('input-email'); setError('') }}
              >
                Back
              </button>
            </div>
          </form>
        )}

        {stage === 'link-sent' && (
          <div style={{ display: 'grid', gap: '14px', marginTop: '10px' }}>
            <h1>Check your email</h1>
            <p>
              We've sent a secure password reset link to <strong>{email}</strong>.
            </p>
            <p className="chat-muted">
              Click the link in the email to set a new password. The link is valid for 15 minutes.
            </p>

            {error && <p className="chat-error" role="alert">{error}</p>}

            <button
              type="button"
              className="matches-outline-button"
              disabled={resendCountdown > 0 || busy}
              onClick={() => void handleSendRecovery('link')}
            >
              {resendCountdown > 0 ? `Resend email (${resendCountdown}s)` : 'Resend reset link'}
            </button>

            <button
              type="button"
              className="matches-primary-button login-primary-button"
              onClick={() => navigate('/login')}
            >
              Return to Login
            </button>
          </div>
        )}

        {stage === 'reset-success' && (
          <div style={{ display: 'grid', gap: '14px', marginTop: '10px', textAlign: 'center' }}>
            <h1>Password updated!</h1>
            <p style={{ color: '#8ae2b8' }}>
              Your password has been reset successfully. You can now sign in with your new password.
            </p>
            <button
              type="button"
              className="matches-primary-button login-primary-button"
              onClick={() => navigate('/login')}
            >
              Sign In Now
            </button>
          </div>
        )}

        <p className="login-signup-copy" style={{ marginTop: '20px' }}>
          Remembered your password? <Link to="/login">Sign in</Link>
        </p>
        <Link className="matches-back-link login-back-link" to="/">Back to Raahi home</Link>
      </Card>
    </PageContainer>
  )
}
