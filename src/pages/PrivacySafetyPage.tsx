import { useState } from 'react'
import { Link } from 'react-router'
import './privacy-help.css'

export function PrivacySafetyPage() {
  const [ghostMode, setGhostMode] = useState(false)
  const [incognitoSearch, setIncognitoSearch] = useState(false)
  const [screenshotProtection, setScreenshotProtection] = useState(true)
  const [readReceipts, setReadReceipts] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  function showToast(msg: string) {
    setToastMessage(msg)
    window.setTimeout(() => setToastMessage(null), 3000)
  }

  return (
    <section className="privacy-page page-enter" aria-label="Privacy and Safety Center">
      {toastMessage && (
        <div className="discover-feedback-toast" role="status">
          {toastMessage}
        </div>
      )}

      <header className="privacy-header">
        <Link to="/discover" className="privacy-back-link">
          ← Back to Discover
        </Link>
        <p className="integration-eyebrow">SECURITY & CONTROLS</p>
        <h1 className="privacy-title">Privacy & Safety</h1>
        <p className="privacy-subtitle">
          Your wellbeing and data sovereignty come first. Manage your visibility, safe-dating protocols, and confidentiality on Raahi.
        </p>
      </header>

      {/* 1. VISIBILITY & DISCOVERY */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">👻</span>
          <div>
            <h2 className="privacy-card-title">Discovery & Visibility</h2>
            <p className="privacy-card-desc">Control when, where, and to whom your profile appears.</p>
          </div>
        </div>

        <div className="privacy-row">
          <div className="privacy-row-info">
            <strong>Ghost Mode (Invisible Browsing)</strong>
            <span>Browse candidate profiles without updating your last-seen time or revealing online status.</span>
          </div>
          <label className="privacy-switch" aria-label="Toggle Ghost Mode">
            <input
              type="checkbox"
              checked={ghostMode}
              onChange={e => {
                setGhostMode(e.target.checked)
                showToast(e.target.checked ? 'Ghost Mode enabled 👻' : 'Ghost Mode disabled')
              }}
            />
            <span className="privacy-switch-slider" />
          </label>
        </div>

        <div className="privacy-row">
          <div className="privacy-row-info">
            <strong>Incognito Search</strong>
            <span>Prevent your profile from appearing in the general search directory until you like someone.</span>
          </div>
          <label className="privacy-switch" aria-label="Toggle Incognito Search">
            <input
              type="checkbox"
              checked={incognitoSearch}
              onChange={e => {
                setIncognitoSearch(e.target.checked)
                showToast(e.target.checked ? 'Incognito Search activated 🕵️' : 'Incognito Search turned off')
              }}
            />
            <span className="privacy-switch-slider" />
          </label>
        </div>

        <div className="privacy-row">
          <div className="privacy-row-info">
            <strong>Read Receipts</strong>
            <span>Display double checkmarks when messages you send or receive are opened.</span>
          </div>
          <label className="privacy-switch" aria-label="Toggle Read Receipts">
            <input
              type="checkbox"
              checked={readReceipts}
              onChange={e => {
                setReadReceipts(e.target.checked)
                showToast(e.target.checked ? 'Read receipts enabled ✓✓' : 'Read receipts disabled')
              }}
            />
            <span className="privacy-switch-slider" />
          </label>
        </div>
      </div>

      {/* 2. CHAT & CONTENT PROTECTION */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">🛡️</span>
          <div>
            <h2 className="privacy-card-title">Media & Content Protection</h2>
            <p className="privacy-card-desc">Safeguard photos, voice notes, and conversations.</p>
          </div>
        </div>

        <div className="privacy-row">
          <div className="privacy-row-info">
            <strong>Screenshot & Media Shield</strong>
            <span>Notify you and restrict instant capture when media is shared in private messages.</span>
          </div>
          <label className="privacy-switch" aria-label="Toggle Screenshot Shield">
            <input
              type="checkbox"
              checked={screenshotProtection}
              onChange={e => {
                setScreenshotProtection(e.target.checked)
                showToast(e.target.checked ? 'Media Shield active 🛡️' : 'Media Shield disabled')
              }}
            />
            <span className="privacy-switch-slider" />
          </label>
        </div>

        <div className="privacy-info-box">
          <span className="privacy-info-icon" aria-hidden="true">🔒</span>
          <div>
            <strong>End-to-End Chat Encryption</strong>
            <p>
              All direct conversations between you and mutual matches are secured with AES-256 in-transit encryption. Only you and your match hold decryption authorization.
            </p>
          </div>
        </div>
      </div>

      {/* 3. SAFE DATING GUIDELINES */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">🤝</span>
          <div>
            <h2 className="privacy-card-title">Safe Dating Guidelines</h2>
            <p className="privacy-card-desc">Practical tips for a safe, respectful dating experience.</p>
          </div>
        </div>

        <div className="privacy-guidelines-grid">
          <div className="privacy-guide-item">
            <span className="guide-icon">📍</span>
            <strong>Meet in Public</strong>
            <p>For your first few dates, choose well-lit public venues like cafes or restaurants. Never meet in private residences.</p>
          </div>

          <div className="privacy-guide-item">
            <span className="guide-icon">📲</span>
            <strong>Share Your Itinerary</strong>
            <p>Always tell a close friend or family member where you are going, who you are meeting, and share live location.</p>
          </div>

          <div className="privacy-guide-item">
            <span className="guide-icon">💳</span>
            <strong>Never Send Money</strong>
            <p>Never send cryptocurrency, wire transfers, or financial aid to anyone you meet online, regardless of their story.</p>
          </div>

          <div className="privacy-guide-item">
            <span className="guide-icon">✅</span>
            <strong>Look for Verification</strong>
            <p>Prioritize interacting with profiles that carry Raahi's verified badge ✦, indicating confirmed identity.</p>
          </div>
        </div>
      </div>

      {/* 4. REPORTING & BLOCKING */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">🚫</span>
          <div>
            <h2 className="privacy-card-title">Zero-Tolerance Safety Policy</h2>
            <p className="privacy-card-desc">Harassment, hate speech, fraud, and impersonation lead to immediate permanent ban.</p>
          </div>
        </div>

        <p className="privacy-copy">
          You can block or report any profile at any time by opening their profile card or chat menu and selecting <strong>Block User</strong> or <strong>Report to Trust & Safety</strong>. Reports are handled with top priority.
        </p>
        <div className="privacy-actions">
          <Link to="/settings" className="privacy-action-btn">
            Manage Blocked Users in Settings →
          </Link>
        </div>
      </div>
    </section>
  )
}
export default PrivacySafetyPage
