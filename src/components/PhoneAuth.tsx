import { useState, useEffect, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { sendPhoneOtp, verifyPhoneOtp } from '../api/auth'

interface PhoneAuthProps {
  isRegistration?: boolean
  onSuccess: (token: string, isNewUser: boolean) => void | Promise<void>
  onSwitchToEmail?: () => void
}

export function PhoneAuth({ isRegistration = false, onSuccess, onSwitchToEmail }: PhoneAuthProps) {
  const [phone, setPhone] = useState('+91')
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState<'phone' | 'otp'>('phone')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => setCountdown(c => c - 1), 1000)
    return () => clearInterval(timer)
  }, [countdown])

  async function handleSendOtp(event?: FormEvent) {
    if (event) event.preventDefault()
    setError('')
    const trimmedPhone = phone.trim()
    if (!/^\+[1-9]\d{6,14}$/.test(trimmedPhone)) {
      setError('Please enter a valid phone number with country code (e.g. +919876543210).')
      return
    }
    if (isRegistration && fullName.trim().length > 0 && fullName.trim().length < 2) {
      setError('Name must be at least 2 characters.')
      return
    }

    setBusy(true)
    try {
      await sendPhoneOtp(trimmedPhone)
      setStep('otp')
      setCountdown(60)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not send verification SMS. Check connection.')
    } finally {
      setBusy(false)
    }
  }

  async function handleVerifyOtp(event: FormEvent) {
    event.preventDefault()
    setError('')
    const trimmedOtp = otp.trim()
    if (!/^\d{6}$/.test(trimmedOtp)) {
      setError('Please enter the 6-digit code received via SMS.')
      return
    }

    setBusy(true)
    try {
      const result = await verifyPhoneOtp({
        phone_number: phone.trim(),
        otp: trimmedOtp,
        full_name: fullName.trim() || undefined,
        username: username.trim() || undefined,
      })
      await onSuccess(result.access_token, result.is_new_user)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Verification failed. Check the code and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="phone-auth-container">
      {step === 'phone' ? (
        <form className="account-login-form" onSubmit={handleSendOtp}>
          {isRegistration && (
            <>
              <label>
                Full Name
                <input
                  type="text"
                  autoComplete="name"
                  placeholder="Your Name"
                  maxLength={80}
                  value={fullName}
                  onChange={e => setFullName(e.currentTarget.value)}
                />
              </label>
              <label>
                Username (optional)
                <input
                  type="text"
                  autoComplete="username"
                  placeholder="e.g. rohan_vibe"
                  maxLength={30}
                  value={username}
                  onChange={e => setUsername(e.currentTarget.value)}
                />
              </label>
            </>
          )}
          <label>
            Phone Number (with country code)
            <input
              type="tel"
              autoComplete="tel"
              placeholder="+919876543210"
              value={phone}
              onChange={e => setPhone(e.currentTarget.value)}
              required
            />
          </label>
          {error && <p className="chat-error" role="alert">{error}</p>}
          <button type="submit" className="matches-primary-button login-primary-button" disabled={busy}>
            {busy ? 'Sending SMS code…' : 'Send verification code'}
          </button>
          {onSwitchToEmail && (
            <button type="button" className="matches-outline-button" onClick={onSwitchToEmail}>
              Use Email & Password instead
            </button>
          )}
          <p className="chat-muted">We will send a 6-digit one-time code to verify your phone number.</p>
        </form>
      ) : (
        <form className="account-login-form" onSubmit={handleVerifyOtp}>
          <p className="chat-muted" style={{ margin: '0 0 10px' }}>
            Verification code sent to <strong>{phone}</strong>.{' '}
            <button
              type="button"
              className="chat-link"
              style={{ background: 'none', border: 'none', color: 'var(--ep)', cursor: 'pointer', padding: 0 }}
              onClick={() => { setStep('phone'); setOtp(''); setError('') }}
            >
              Change
            </button>
          </p>
          <label>
            6-Digit Verification Code
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
          {error && <p className="chat-error" role="alert">{error}</p>}
          <button type="submit" className="matches-primary-button login-primary-button" disabled={busy}>
            {busy ? 'Verifying…' : 'Verify & Continue'}
          </button>
          <div className="auth-action-row">
            <button
              type="button"
              className="matches-outline-button"
              disabled={countdown > 0 || busy}
              onClick={() => void handleSendOtp()}
              style={{ fontSize: '.84rem' }}
            >
              {countdown > 0 ? `Resend code (${countdown}s)` : 'Resend SMS code'}
            </button>
            {onSwitchToEmail && (
              <button
                type="button"
                className="chat-link"
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,.7)', cursor: 'pointer', fontSize: '.84rem' }}
                onClick={onSwitchToEmail}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  )
}
