import { useState } from 'react'
import { Link } from 'react-router'
import { useTheme } from '../state/ThemeContext'
import { generationThemes } from '../data/generations'
import './privacy-help.css'

export function HelpSupportPage() {
  const { generation } = useTheme()
  const theme = generationThemes[generation] || generationThemes.genz
  const [expandedFaq, setExpandedFaq] = useState<number | null>(0)
  const [feedbackText, setFeedbackText] = useState('')
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  function showToast(msg: string) {
    setToastMessage(msg)
    window.setTimeout(() => setToastMessage(null), 3000)
  }

  function handleSendFeedback(e: React.FormEvent) {
    e.preventDefault()
    if (!feedbackText.trim()) return
    showToast('Thank you for your feedback! Our support team has received your note. 💖')
    setFeedbackText('')
  }

  const faqs = [
    {
      q: 'How does Raahi’s era matching algorithm work?',
      a: 'Raahi matches you using generation-aligned sensibilities—Gen Z, Zillennial, and Millennial. Profiles share compatible relationship expectations, situational humor, and communication paces tailored to your era vibe.'
    },
    {
      q: 'How do I change my global app theme or era palette?',
      a: 'Open the hamburger menu ☰, choose Settings, and navigate to the Appearance section. You can switch between Gen Z (Cosmic Purple), Zillennial (Warm Amber / Coral), and Millennial (Cyan / Azure) with a single tap.'
    },
    {
      q: 'What is the Raahi Verification Badge ✦?',
      a: 'A verified badge indicates the member has completed biometric or document identity verification. Verified accounts help keep the Raahi community authentic and free from automated spam.'
    },
    {
      q: 'How does the AI Conversation Wingman work?',
      a: 'When messaging a match, tap the sparkle ✨ icon in the composer to access AI icebreakers, tailored witty replies, and vibe check openers generated from shared profile interests.'
    },
    {
      q: 'How do I block or report someone who behaves inappropriately?',
      a: 'You can immediately block or report any profile directly from their conversation header settings pill or profile details view. Blocked users cannot view your profile or message you.'
    }
  ]

  return (
    <section className="privacy-page page-enter" aria-label="Help and Support Center">
      {toastMessage && (
        <div className="discover-feedback-toast" role="status">
          {toastMessage}
        </div>
      )}

      <header className="privacy-header">
        <Link to="/discover" className="privacy-back-link">
          ← Back to Discover
        </Link>
        <p className="integration-eyebrow">RAAHI ASSISTANCE</p>
        <h1 className="privacy-title">Help & Support</h1>
        <p className="privacy-subtitle">
          Got questions or need a hand? Explore frequently asked questions, safe-dating guidance, or reach our concierge support team.
        </p>
      </header>

      {/* 1. FAQS */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">💡</span>
          <div>
            <h2 className="privacy-card-title">Frequently Asked Questions</h2>
            <p className="privacy-card-desc">Quick answers to common questions about Raahi.</p>
          </div>
        </div>

        <div className="help-faq-list">
          {faqs.map((faq, index) => {
            const isOpen = expandedFaq === index
            return (
              <div key={index} className={`help-faq-item${isOpen ? ' open' : ''}`}>
                <button
                  type="button"
                  className="help-faq-btn"
                  onClick={() => setExpandedFaq(isOpen ? null : index)}
                  aria-expanded={isOpen}
                >
                  <span className="help-faq-q">{faq.q}</span>
                  <span className="help-faq-toggle" aria-hidden="true">
                    {isOpen ? '−' : '+'}
                  </span>
                </button>
                {isOpen && (
                  <div className="help-faq-answer">
                    <p>{faq.a}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* 2. DIRECT CONTACT & CONCIERGE */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">💬</span>
          <div>
            <h2 className="privacy-card-title">Direct Support & Feedback</h2>
            <p className="privacy-card-desc">Send feedback or report a bug directly to our product engineers.</p>
          </div>
        </div>

        <form onSubmit={handleSendFeedback} className="help-feedback-form">
          <label htmlFor="help-feedback-input" className="help-feedback-label">
            Describe your issue or suggestion:
          </label>
          <textarea
            id="help-feedback-input"
            rows={4}
            value={feedbackText}
            onChange={e => setFeedbackText(e.target.value)}
            placeholder="Tell us what happened or how we can make Raahi better for you…"
            className="help-feedback-textarea"
            required
          />
          <button type="submit" className="help-feedback-submit-btn">
            Send to Support 🚀
          </button>
        </form>

        <div className="help-contact-row">
          <div className="help-contact-method">
            <span className="method-icon">✉️</span>
            <div>
              <strong>Email Support</strong>
              <span>support@raahi.app</span>
            </div>
          </div>
          <div className="help-contact-method">
            <span className="method-icon">🛡️</span>
            <div>
              <strong>Safety Escalations</strong>
              <span>safety@raahi.app</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. SYSTEM STATUS & VERSION */}
      <div className="privacy-card">
        <div className="privacy-card-header">
          <span className="privacy-card-icon" aria-hidden="true">🟢</span>
          <div>
            <h2 className="privacy-card-title">Platform Status</h2>
            <p className="privacy-card-desc">Real-time status of Raahi infrastructure and services.</p>
          </div>
        </div>

        <div className="help-status-grid">
          <div className="help-status-item">
            <span className="status-dot green" />
            <span className="status-label">Dating Engine V3</span>
            <span className="status-state">Operational</span>
          </div>
          <div className="help-status-item">
            <span className="status-dot green" />
            <span className="status-label">WebSocket Chat Server</span>
            <span className="status-state">Operational</span>
          </div>
          <div className="help-status-item">
            <span className="status-dot green" />
            <span className="status-label">Identity Verification</span>
            <span className="status-state">Operational</span>
          </div>
        </div>
        <p className="help-version-note">
          Raahi Web App build <code>v0.1.0-alpha</code> · Theme: <strong>{theme.name}</strong>
        </p>
      </div>
    </section>
  )
}
export default HelpSupportPage
