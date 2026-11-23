import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import CoupleIllustration from '../components/CoupleIllustration'
import EditNameModal from '../components/EditNameModal'
import { Button } from '../components/Button'
import StarField from '../components/StarField'
import { RaahiWordmark } from '../components/RaahiWordmark'

const NAME_KEY = 'raahiAppName'
const ACTIVE_KEY = 'raahiLastActive'
const INACTIVE_DAYS = 7
const googleGIcon = new URL('../assets/google-g.svg', import.meta.url).href

function readStoredName() {
  try { return localStorage.getItem(NAME_KEY) || 'raahi' } catch { return 'raahi' }
}

function checkInactivity() {
  try {
    const lastActive = localStorage.getItem(ACTIVE_KEY)
    if (!lastActive) {
      localStorage.setItem(ACTIVE_KEY, String(Date.now()))
      return false
    }
    const daysSince = (Date.now() - Number.parseInt(lastActive, 10)) / 86_400_000
    return Number.isFinite(daysSince) && daysSince >= INACTIVE_DAYS
  } catch {
    return false
  }
}

function setActiveNow() {
  try { localStorage.setItem(ACTIVE_KEY, String(Date.now())) } catch { /* Storage can be disabled by the browser. */ }
}

function vibrate(pattern: number | number[]) {
  if ('vibrate' in navigator) navigator.vibrate(pattern)
}

export default function LandingPage() {
  const navigate = useNavigate()
  const [appName, setAppName] = useState(readStoredName)
  const [nameDraft, setNameDraft] = useState(readStoredName)
  const [modalOpen, setModalOpen] = useState(false)
  const [inactive, setInactive] = useState(checkInactivity)

  const closeModal = useCallback(() => setModalOpen(false), [])

  function openModal() {
    setNameDraft(appName)
    setModalOpen(true)
  }

  function saveName() {
    const value = nameDraft.trim()
    if (value) {
      setAppName(value)
      try { localStorage.setItem(NAME_KEY, value) } catch { /* Keep the edit for this session if storage is unavailable. */ }
    }
    setModalOpen(false)
  }

  function toggleInactive() {
    if (inactive) {
      setActiveNow()
      setInactive(false)
      return
    }
    try { localStorage.setItem(ACTIVE_KEY, String(Date.now() - 8 * 86_400_000)) } catch { /* The visual simulation still works without storage. */ }
    setInactive(true)
  }

  function handleGetStarted() {
    setActiveNow()
    setInactive(false)
    vibrate(30)
    navigate('/register')
  }

  function handleLogin() {
    setActiveNow()
    vibrate(20)
    navigate('/login')
  }

  function handleGoogle() {
    setActiveNow()
    vibrate(20)
    navigate('/login?provider=google')
  }

  return (
    <main className={`landing-screen flex flex-col items-center justify-between${inactive ? ' inactive' : ''}`}>
      <StarField />

      <header className="top">
        <div className="sparkle-icon" aria-hidden="true">✦✦</div>
        <button className="brand" id="brandName" title="Tap to edit name" onClick={openModal}>
          <RaahiWordmark label={appName} />
        </button>
        <div className="tagline">No Ghosting. Just Vibes.</div>
      </header>

      <CoupleIllustration />

      <div className="buttons">
        <Button variant="primary" onClick={handleGetStarted}>Let's get it 🔥</Button>
        <Button variant="secondary" onClick={handleLogin}>Already got a vibe? Log in</Button>
        <Button variant="google" className="google-signup-btn" onClick={handleGoogle}>
          <span className="google-signup-content">
            <img className="google-g-icon" src={googleGIcon} alt="" aria-hidden="true" />
            <span>Continue with Google</span>
          </span>
        </Button>
        <p className="footer-note">IT Act 2000 &amp; IT Rules 2021 compliant · 18+ only</p>
      </div>

      <EditNameModal
        open={modalOpen}
        value={nameDraft}
        onChange={setNameDraft}
        onClose={closeModal}
        onSave={saveName}
      />

      <button
        className="dev-toggle"
        id="devBtn"
        onClick={toggleInactive}
        title="Simulate 7-day inactivity"
        aria-pressed={inactive}
      >
        {inactive ? '✅ Active Mode' : '👁 Test Inactive'}
      </button>
    </main>
  )
}
