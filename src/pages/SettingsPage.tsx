import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useAuth } from '../state/AuthContext'
import { generationThemes, type GenerationId } from '../data/generations'
import { readDemoProfile, writeDemoProfile } from '../data/userProfile'
import { useTheme } from '../state/ThemeContext'
import { getBlockedUsers, unblockUser, resetAllDemoData } from '../data/demoAppData'
import './settings.css'

export function SettingsPage() {
  const { generation, setGeneration } = useTheme()
  const { user, updateUser, logout } = useAuth()
  const navigate = useNavigate()

  const [profile, setProfile] = useState(() => readDemoProfile())
  const [displayName, setDisplayName] = useState(() => profile?.name ?? 'onkarnagargoje12')
  const [bio, setBio] = useState(() => profile?.bio ?? 'A short bio..')
  const [savingProfile, setSavingProfile] = useState(false)
  const [expandedProfile, setExpandedProfile] = useState(false)
  const [expandedBlocked, setExpandedBlocked] = useState(false)

  // Appearance
  const [darkMode, setDarkMode] = useState(true)

  // AI & Privacy
  const [personalAiMemory, setPersonalAiMemory] = useState(() => user?.ai_memory_enabled ?? true)
  const [externalAiProcessing, setExternalAiProcessing] = useState(() => user?.ai_provider_processing_enabled ?? true)

  // Privacy & Safety
  const [notifications, setNotifications] = useState(true)
  const [matchCelebrations, setMatchCelebrations] = useState(true)
  const [readReceipts, setReadReceipts] = useState(true)
  const [ghostMode, setGhostMode] = useState(false)

  // Blocked users
  const [blockedList, setBlockedList] = useState<string[]>(() => getBlockedUsers())

  // Feedback Toast
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  function showToast(msg: string) {
    setToastMessage(msg)
    window.setTimeout(() => setToastMessage(null), 3000)
  }

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault()
    setSavingProfile(true)
    if (profile) {
      const updated = writeDemoProfile(
        { ...profile, name: displayName.trim(), bio: bio.trim() },
        profile
      )
      if (updated) {
        setProfile(updated)
        showToast('Profile saved successfully! ✨')
        setExpandedProfile(false)
      }
    }
    setSavingProfile(false)
  }

  async function toggleAiConsent(field: 'ai_provider_processing_enabled' | 'ai_memory_enabled', value: boolean) {
    if (field === 'ai_memory_enabled') setPersonalAiMemory(value)
    else setExternalAiProcessing(value)

    if (user) {
      try {
        await updateUser({ [field]: value })
        showToast('Preference saved to account.')
      } catch {
        showToast('Failed to save to server, saved locally.')
      }
    } else {
      showToast('Saved to local preferences.')
    }
  }

  function handleUnblock(username: string) {
    const next = unblockUser(username)
    setBlockedList(next)
    showToast(`Unblocked @${username}`)
  }

  function handleResetDemo() {
    if (!window.confirm('Reset all demo swipe deck and test matches?')) return
    resetAllDemoData()
    showToast('Demo data reset to clean state!')
  }

  function handleLogout() {
    logout()
    showToast('Logged out of session.')
    navigate('/login')
  }

  function handleDeleteAccount() {
    if (!window.confirm('Are you sure you want to delete your account? This action cannot be undone.')) return
    resetAllDemoData()
    logout()
    showToast('Account data removed.')
    navigate('/')
  }

  const theme = generationThemes[generation] || generationThemes.genz
  const userInitial = displayName.trim()[0]?.toUpperCase() || '😎'

  return (
    <section className="settings-screen page-enter" aria-label="Application Settings">
      {toastMessage && (
        <div className="discover-feedback-toast" role="status">
          {toastMessage}
        </div>
      )}

      {/* Back Link to Profile */}
      <Link to="/profile" className="settings-back-link">
        <span className="e e-swing" aria-hidden="true">←</span> Back to Profile
      </Link>

      {/* Page Header */}
      <header className="settings-page-header fiu">
        <div>
          <p className="integration-eyebrow">PREFERENCES & SAFETY</p>
          <h1 className="settings-page-title">Settings</h1>
          <p className="settings-page-subtitle">Configure your vibe, conversation AI, and privacy controls</p>
        </div>
        <span className="settings-mode-pill">
          {theme.name.toUpperCase()}
        </span>
      </header>

      {/* Top User Hero Card */}
      <div className="settings-user-hero">
        <div className="settings-user-hero-left">
          <div
            className="settings-avatar-circle"
            style={{ borderColor: theme.primary, boxShadow: `0 0 18px ${theme.glow}` }}
          >
            <span>{userInitial === 'O' ? '😎' : userInitial}</span>
          </div>
          <div>
            <h2 className="settings-user-name">{displayName}</h2>
            <p className="settings-user-sub">
              @{user?.username || 'onkarnagargoje12'} · {theme.name} Vibe
            </p>
          </div>
        </div>
        <Link to="/profile/edit" className="settings-edit-pill" aria-label="Edit Full Profile">
          ✏️ Edit Profile
        </Link>
      </div>

      {/* 1. SECTION: ACCOUNT */}
      <div className="settings-group">
        <h3 className="settings-group-title">Account</h3>
        <div className="settings-group-card">
          <div
            className="settings-row clickable"
            onClick={() => setExpandedProfile(prev => !prev)}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') setExpandedProfile(prev => !prev) }}
            aria-expanded={expandedProfile}
          >
            <div className="settings-row-icon" aria-hidden="true">👤</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Display Name & Bio</span>
              <span className="settings-row-desc">Quick editor for your name and mini-bio</span>
            </div>
            <div className="settings-row-ctrl">
              <span className={`settings-chevron${expandedProfile ? ' expanded' : ''}`} aria-hidden="true">›</span>
            </div>
          </div>

          {expandedProfile && (
            <form onSubmit={handleSaveProfile} className="settings-row-expandable">
              <label className="settings-mini-field">
                <span>Display Name</span>
                <input
                  type="text"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  maxLength={30}
                  placeholder="Your display name"
                />
              </label>
              <label className="settings-mini-field">
                <span>Bio</span>
                <textarea
                  value={bio}
                  onChange={e => setBio(e.target.value)}
                  maxLength={200}
                  rows={2}
                  placeholder="Write a short bio.."
                />
              </label>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                <button
                  type="button"
                  className="settings-mini-btn-secondary"
                  onClick={() => setExpandedProfile(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="settings-mini-btn-primary"
                  disabled={savingProfile}
                >
                  {savingProfile ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          )}

          <Link to="/profile/edit" className="settings-row clickable">
            <div className="settings-row-icon" aria-hidden="true">🎨</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Full Profile & Photos</span>
              <span className="settings-row-desc">Manage portraits, prompts, and interest chips</span>
            </div>
            <div className="settings-row-ctrl">
              <span className="settings-chevron" aria-hidden="true">›</span>
            </div>
          </Link>
        </div>
      </div>

      {/* 2. SECTION: PRIVACY & SAFETY */}
      <div className="settings-group">
        <h3 className="settings-group-title">Privacy & Safety</h3>
        <div className="settings-group-card">
          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">👻</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Ghost Mode</span>
              <span className="settings-row-desc">Hide online and last seen activity from matches</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Ghost Mode">
                <input
                  type="checkbox"
                  checked={ghostMode}
                  onChange={e => {
                    setGhostMode(e.target.checked)
                    showToast(e.target.checked ? 'Ghost mode active 👻' : 'Ghost mode disabled')
                  }}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">✓✓</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Read Receipts</span>
              <span className="settings-row-desc">Show checkmarks when messages are seen</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Read Receipts">
                <input
                  type="checkbox"
                  checked={readReceipts}
                  onChange={e => {
                    setReadReceipts(e.target.checked)
                    showToast(e.target.checked ? 'Read receipts enabled ✓✓' : 'Read receipts disabled')
                  }}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 3. SECTION: NOTIFICATIONS */}
      <div className="settings-group">
        <h3 className="settings-group-title">Notifications</h3>
        <div className="settings-group-card">
          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🔔</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Message Alerts</span>
              <span className="settings-row-desc">In-app notifications for incoming conversation chats</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Message Alerts">
                <input
                  type="checkbox"
                  checked={notifications}
                  onChange={e => {
                    setNotifications(e.target.checked)
                    showToast(e.target.checked ? 'Message alerts enabled 🔔' : 'Message alerts muted 🔕')
                  }}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🎉</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Match Celebrations</span>
              <span className="settings-row-desc">Display celebration popups on mutual sparks</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Match Celebrations">
                <input
                  type="checkbox"
                  checked={matchCelebrations}
                  onChange={e => {
                    setMatchCelebrations(e.target.checked)
                    showToast(e.target.checked ? 'Match celebrations enabled 🎉' : 'Celebrations muted')
                  }}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 4. SECTION: APPEARANCE */}
      <div className="settings-group">
        <h3 className="settings-group-title">Appearance</h3>
        <div className="settings-group-card">
          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🌙</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Dark Mode</span>
              <span className="settings-row-desc">
                {darkMode ? 'Purple night is active · tap for light' : 'Light cosmic mode enabled'}
              </span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Dark Mode">
                <input
                  type="checkbox"
                  checked={darkMode}
                  onChange={e => {
                    setDarkMode(e.target.checked)
                    showToast(e.target.checked ? 'Purple night mode active 🌙' : 'Light cosmic mode enabled ☀️')
                  }}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>

          <div className="settings-theme-section">
            <div className="settings-row">
              <div className="settings-row-icon" aria-hidden="true">{theme.emoji}</div>
              <div className="settings-row-info">
                <span className="settings-row-title">Active Era Theme</span>
                <span className="settings-row-desc">{theme.name} palette · {theme.eraDescription.split('·')[0].trim()}</span>
              </div>
              <div className="settings-row-ctrl">
                <span className="settings-status-pill" style={{ color: theme.primary, borderColor: theme.cardBorder }}>
                  {theme.name}
                </span>
              </div>
            </div>

            <div className="settings-theme-grid" role="radiogroup" aria-label="Choose application theme">
              {(Object.keys(generationThemes) as GenerationId[]).map(themeId => {
                const item = generationThemes[themeId]
                const isSelected = generation === themeId
                return (
                  <button
                    key={themeId}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    className={`settings-theme-option${isSelected ? ' selected' : ''}`}
                    onClick={() => {
                      setGeneration(themeId)
                      showToast(`Switched to ${item.name} theme ✨`)
                    }}
                    style={{
                      '--opt-primary': item.primary,
                      '--opt-secondary': item.secondary,
                      '--opt-glow': item.glow,
                      '--opt-bg': item.background,
                      '--opt-border': item.cardBorder,
                    } as React.CSSProperties}
                  >
                    <div className="theme-option-top">
                      <span className="theme-option-emoji">{item.emoji}</span>
                      <span className="theme-option-radio" aria-hidden="true">
                        {isSelected && <span className="theme-option-radio-dot" />}
                      </span>
                    </div>
                    <strong className="theme-option-name">{item.name}</strong>
                    <div className="theme-option-swatches" aria-hidden="true">
                      <span className="theme-swatch" style={{ background: item.primary }} />
                      <span className="theme-swatch" style={{ background: item.secondary }} />
                      <span className="theme-swatch" style={{ background: item.background }} />
                    </div>
                    <small className="theme-option-tags">{item.eraTags.slice(0, 2).join(' · ')}</small>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* 5. SECTION: CONVERSATION AI */}
      <div className="settings-group">
        <h3 className="settings-group-title">Conversation AI</h3>
        <div className="settings-group-card">
          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">✦</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Personal AI Memory</span>
              <span className="settings-row-desc">Let AI remember useful chat context for tailored suggestions</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle Personal AI Memory">
                <input
                  type="checkbox"
                  checked={personalAiMemory}
                  onChange={e => void toggleAiConsent('ai_memory_enabled', e.target.checked)}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🤖</div>
            <div className="settings-row-info">
              <span className="settings-row-title">AI Suggestion Coach</span>
              <span className="settings-row-desc">Enable external AI processing for icebreakers and advice</span>
            </div>
            <div className="settings-row-ctrl">
              <label className="settings-switch" aria-label="Toggle AI Suggestions Coach">
                <input
                  type="checkbox"
                  checked={externalAiProcessing}
                  onChange={e => void toggleAiConsent('ai_provider_processing_enabled', e.target.checked)}
                />
                <span className="settings-switch-slider" />
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* 6. SECTION: VERIFICATION */}
      <div className="settings-group">
        <h3 className="settings-group-title">Verification</h3>
        <div className="settings-group-card">
          <Link to="/verification" className="settings-row clickable">
            <div className="settings-row-icon" aria-hidden="true">🪪</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Identity & Photo Verification</span>
              <span className="settings-row-desc">Submit selfie & student/work ID for verified badge</span>
            </div>
            <div className="settings-row-ctrl">
              <span className="settings-status-pill" style={{ color: '#4ade80', borderColor: 'rgba(74,222,128,0.25)' }}>
                Review Status
              </span>
              <span className="settings-chevron" aria-hidden="true">›</span>
            </div>
          </Link>
        </div>
      </div>

      {/* 7. SECTION: BLOCKED USERS */}
      <div className="settings-group">
        <h3 className="settings-group-title">Blocked Users</h3>
        <div className="settings-group-card">
          <div
            className="settings-row clickable"
            onClick={() => setExpandedBlocked(prev => !prev)}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') setExpandedBlocked(prev => !prev) }}
            aria-expanded={expandedBlocked}
          >
            <div className="settings-row-icon" aria-hidden="true">🚫</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Restricted Profiles</span>
              <span className="settings-row-desc">
                {blockedList.length ? `${blockedList.length} blocked user${blockedList.length > 1 ? 's' : ''}` : 'No blocked users'}
              </span>
            </div>
            <div className="settings-row-ctrl">
              <span className={`settings-chevron${expandedBlocked ? ' expanded' : ''}`} aria-hidden="true">›</span>
            </div>
          </div>

          {expandedBlocked && (
            <div className="settings-row-expandable">
              <p style={{ margin: '0 0 10px', fontSize: '.74rem', color: 'rgba(255,255,255,.5)' }}>
                Blocked people cannot message you or see your profile in Discover.
              </p>
              {blockedList.length ? (
                <div style={{ display: 'grid', gap: 6 }}>
                  {blockedList.map(username => (
                    <div key={username} className="settings-blocked-item">
                      <span>@{username}</span>
                      <button
                        type="button"
                        className="settings-unblock-btn"
                        onClick={() => handleUnblock(username)}
                      >
                        Unblock
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ margin: 0, fontSize: '.76rem', color: 'rgba(255,255,255,.4)' }}>
                  No blocked profiles.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 8. SECTION: ACCOUNT MANAGEMENT */}
      <div className="settings-group">
        <h3 className="settings-group-title">Account Management</h3>
        <div className="settings-group-card">
          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🔄</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Reset Demo Deck</span>
              <span className="settings-row-desc">Restore sample candidates and test conversations</span>
            </div>
            <div className="settings-row-ctrl">
              <button
                type="button"
                className="settings-ctrl-btn neutral"
                onClick={handleResetDemo}
              >
                Reset
              </button>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🚪</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Sign Out</span>
              <span className="settings-row-desc">Log out of your current session on this device</span>
            </div>
            <div className="settings-row-ctrl">
              <button
                type="button"
                className="settings-ctrl-btn warning"
                onClick={handleLogout}
              >
                Sign Out
              </button>
            </div>
          </div>

          <div className="settings-row">
            <div className="settings-row-icon" aria-hidden="true">🗑️</div>
            <div className="settings-row-info">
              <span className="settings-row-title">Delete Account Data</span>
              <span className="settings-row-desc">Permanently remove your local profile data</span>
            </div>
            <div className="settings-row-ctrl">
              <button
                type="button"
                className="settings-ctrl-btn danger"
                onClick={handleDeleteAccount}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
