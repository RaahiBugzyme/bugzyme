import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { AccountAccess } from '../components/AccountAccess'
import { Card } from '../components/Card'
import { LoadingState } from '../components/LoadingState'
import { PageContainer } from '../components/PageContainer'
import { PhoneAuth } from '../components/PhoneAuth'
import { useAuth } from '../state/AuthContext'
import { useDatingProfile } from '../state/DatingProfileContext'
import { postAuthenticationDestination } from '../routing/onboardingDestination'
import { RaahiWordmark } from '../components/RaahiWordmark'
import { getGoogleAuthUrl, loginWithGoogleCallback } from '../api/auth'
import { ApiError } from '../api/client'

const googleGIcon = new URL('../assets/google-g.svg', import.meta.url).href

export function LoginPage() {
  const { user, loading, logout, loginWithToken } = useAuth()
  const { refreshProfile } = useDatingProfile()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [authMethod, setAuthMethod] = useState<'email' | 'phone'>('email')
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleError, setGoogleError] = useState('')
  const [routeError, setRouteError] = useState('')
  const [accountDestination, setAccountDestination] = useState<string | null>(null)
  const [checkingAccount, setCheckingAccount] = useState(false)
  const requestedPath = searchParams.get('next')

  const resolveDestination = useCallback(async () => {
    const currentProfile = await refreshProfile()
    return postAuthenticationDestination(currentProfile, null, requestedPath)
  }, [refreshProfile, requestedPath])

  // Handle Google OAuth callback if returned with code & state
  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    if (!code || !state || user) return

    let active = true
    setGoogleLoading(true)
    setGoogleError('')

    void (async () => {
      try {
        const result = await loginWithGoogleCallback({ code, state })
        if (!active) return
        await loginWithToken(result.access_token)
        const destination = await resolveDestination()
        if (active) {
          setAccountDestination(destination)
          navigate(destination, { replace: true })
        }
      } catch (cause) {
        if (active) {
          setGoogleError(cause instanceof ApiError ? cause.message : 'Google sign-in failed. Please try again or use email.')
        }
      } finally {
        if (active) setGoogleLoading(false)
      }
    })()

    return () => { active = false }
  }, [searchParams, user, loginWithToken, resolveDestination, navigate])

  useEffect(() => {
    if (loading || !user) return
    let active = true
    setCheckingAccount(true)
    setRouteError('')
    void resolveDestination().then(destination => {
      if (active) setAccountDestination(destination)
    }).catch(reason => {
      if (active) setRouteError(reason instanceof Error ? reason.message : 'Could not check your saved profile.')
    }).finally(() => { if (active) setCheckingAccount(false) })
    return () => { active = false }
  }, [loading, user, resolveDestination])

  async function afterLogin() {
    setRouteError('')
    try {
      const destination = await resolveDestination()
      setAccountDestination(destination)
      navigate(destination, { replace: true })
    } catch (reason) {
      setRouteError(reason instanceof Error ? reason.message : 'Signed in, but account setup could not be checked. Try again.')
    }
  }

  async function handleGoogleSignIn() {
    setGoogleError('')
    setGoogleLoading(true)
    try {
      const data = await getGoogleAuthUrl()
      if (data.authorization_url) {
        window.location.href = data.authorization_url
      } else {
        setGoogleError('Could not retrieve Google authorization URL.')
      }
    } catch (cause) {
      setGoogleError(cause instanceof ApiError ? cause.message : 'Google sign-in is not available right now. Please sign in with email or phone.')
    } finally {
      setGoogleLoading(false)
    }
  }

  if (loading || googleLoading) return <LoadingState label={googleLoading ? 'Signing in with Google…' : 'Checking your Raahi session…'} />

  if (user) return (
    <PageContainer className="matches-page matches-auth-page">
      <Card className="matches-empty-card matches-auth-card login-auth-card">
        <div className="login-branding">
          <RaahiWordmark className="login-wordmark" />
          <span>NO GHOSTING. JUST VIBES.</span>
        </div>
        <p className="integration-eyebrow">ACCOUNT SESSION</p>
        <h1>You’re already signed in</h1>
        <p>Signed in as <strong>{user.full_name || user.username}</strong>.</p>
        {checkingAccount && <p role="status" className="chat-muted">Checking your profile and verification status…</p>}
        {routeError && (
          <>
            <p className="chat-error" role="alert">{routeError}</p>
            <button className="matches-outline-button" onClick={() => void afterLogin()}>Try again</button>
          </>
        )}
        {accountDestination && !checkingAccount && (
          <button className="matches-primary-button login-primary-button" onClick={() => navigate(accountDestination, { replace: true })}>
            Continue to your account
          </button>
        )}
        <button className="matches-outline-button login-switch-account" onClick={logout}>Sign out to use another account</button>
      </Card>
    </PageContainer>
  )

  return (
    <PageContainer className="matches-page matches-auth-page page-enter">
      <Card className="matches-empty-card matches-auth-card login-auth-card card-enter">
        <div className="login-branding">
          <RaahiWordmark className="login-wordmark" />
          <span>NO GHOSTING. JUST VIBES.</span>
        </div>
        <p className="integration-eyebrow">WELCOME BACK</p>
        <h1>Sign in to continue</h1>
        <p>Sign in to continue to your saved profile and conversations.</p>

        <div className="auth-method-switcher" role="tablist" aria-label="Sign-in methods">
          <button
            type="button"
            role="tab"
            aria-selected={authMethod === 'email'}
            className={`auth-method-tab${authMethod === 'email' ? ' active' : ''}`}
            onClick={() => setAuthMethod('email')}
          >
            Email & Password
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={authMethod === 'phone'}
            className={`auth-method-tab${authMethod === 'phone' ? ' active' : ''}`}
            onClick={() => setAuthMethod('phone')}
          >
            Phone SMS OTP
          </button>
        </div>

        {googleError && <p className="chat-error" role="alert" style={{ margin: '8px 0' }}>{googleError}</p>}

        {authMethod === 'email' ? (
          <AccountAccess onSignedIn={afterLogin} />
        ) : (
          <PhoneAuth
            isRegistration={false}
            onSuccess={async (token) => {
              await loginWithToken(token)
              await afterLogin()
            }}
            onSwitchToEmail={() => setAuthMethod('email')}
          />
        )}

        <div style={{ margin: '14px 0 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,.12)' }} />
          <span style={{ fontSize: '.72rem', color: 'rgba(255,255,255,.45)', textTransform: 'uppercase', letterSpacing: '.1em' }}>or</span>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,.12)' }} />
        </div>

        <button
          type="button"
          className="login-google-button"
          disabled={googleLoading}
          onClick={() => void handleGoogleSignIn()}
        >
          <img src={googleGIcon} alt="" aria-hidden="true" />
          {googleLoading ? 'Connecting to Google…' : 'Continue with Google'}
        </button>

        <p className="login-signup-copy">Don't have an account? <Link to="/register">Sign up</Link></p>
        <Link className="matches-back-link login-back-link" to="/">Back to Raahi home</Link>
      </Card>
    </PageContainer>
  )
}
