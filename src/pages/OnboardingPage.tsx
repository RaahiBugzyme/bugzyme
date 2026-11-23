import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { createDatingProfile, updateDatingProfile, uploadProfilePhoto, type DatingProfileInput, type DatingGender } from '../api/datingProfile'
import { useAuth } from '../state/AuthContext'
import { useDatingProfile } from '../state/DatingProfileContext'
import { useTheme } from '../state/ThemeContext'
import { generationThemes, type GenerationId } from '../data/generations'
import { validateDateOfBirth, mapApiValidationErrors, getMaxSelectableDob } from '../utils/dobValidation'
import '../styles/onboarding-flow.css'
import '../styles/match-era.css'

type Draft = { era?: GenerationId; vibe?: string; target?: string; matchEra?: string }
const DRAFT_KEY = 'raahi.onboardingDraft.v2'
function readDraft(): Draft {
  try { return JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? '{}') as Draft } catch { return {} }
}
function saveDraft(draft: Draft) {
  try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) } catch { /* API remains the source of truth after completion. */ }
}
function normalizeStep(value: string | undefined) {
  return ['era', 'situationship', 'preferences', 'profile'].includes(value ?? '') ? value! : 'era'
}

export default function OnboardingPage() {
  const step = normalizeStep(useParams().step)
  const navigate = useNavigate()
  const { user, updateUser } = useAuth()
  const { profile, loading: profileLoading, refreshProfile, setProfile } = useDatingProfile()
  const { generation, setGeneration } = useTheme()
  const [draft, setDraft] = useState<Draft>(readDraft)
  const selectedEra = draft.era ?? profile?.era ?? generation
  const selectedTheme = generationThemes[selectedEra]
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [dob, setDob] = useState(profile?.date_of_birth ?? '')
  const [dobError, setDobError] = useState('')
  const [gender, setGender] = useState<DatingGender>(profile?.gender ?? 'prefer_not_to_say')
  const [targetGender, setTargetGender] = useState(profile?.target_gender_preference ?? draft.target ?? 'any')
  const [city, setCity] = useState(profile?.city ?? '')
  const [bio, setBio] = useState(user?.bio ?? '')
  const [matchEra, setMatchEra] = useState(profile?.match_era_preference ?? 'any')
  const [photos, setPhotos] = useState<File[]>([])
  const [photoProgress, setPhotoProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    setGeneration(selectedEra)
  }, [selectedEra, setGeneration])

  useEffect(() => {
    if (!profile) return
    setDob(profile.date_of_birth ?? '')
    setDobError('')
    setGender(profile.gender)
    setTargetGender(profile.target_gender_preference ?? 'any')
    setCity(profile.city)
    setMatchEra(profile.match_era_preference)
  }, [profile])

  const stepIndex = ['era', 'situationship', 'preferences', 'profile'].indexOf(step)

  function updateDraft(changes: Draft) {
    setDraft(current => {
      const next = { ...current, ...changes }
      saveDraft(next)
      return next
    })
  }

  function next(to: string) {
    setError('')
    setDobError('')
    navigate(`/onboarding/${to}`)
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSuccess('')
    setDobError('')

    if (fullName.trim().length < 2) return setError('Enter a name with at least 2 characters.')
    if (!dob) {
      setDobError('Please enter a valid date of birth.')
      return setError('Please enter a valid date of birth.')
    }
    const dobCheck = validateDateOfBirth(dob)
    if (!dobCheck.valid) {
      setDobError(dobCheck.error!)
      return setError(dobCheck.error!)
    }
    if (!city.trim()) return setError('Location is required.')
    if (bio.length > 500) return setError('Bio must be 500 characters or fewer.')
    setBusy(true)
    try {
      const payload: DatingProfileInput = {
        date_of_birth: dob, gender, city: city.trim(), era: selectedEra,
        vibe_tag: draft.vibe ?? profile?.vibe_tag ?? '',
        target_gender_preference: targetGender,
        match_era_preference: draft.matchEra ?? profile?.match_era_preference ?? matchEra,
      }
      const saved = profile ? await updateDatingProfile(payload) : await createDatingProfile(payload)
      setProfile(saved)
      await updateUser({ full_name: fullName.trim(), bio: bio.trim() })
      if (photos.length) {
        for (const file of photos) await uploadProfilePhoto(file, setPhotoProgress)
      }
      try { sessionStorage.removeItem(DRAFT_KEY) } catch { /* ignore unavailable storage */ }
      await refreshProfile()
      setSuccess('Your profile details are saved. Continue to identity verification.')
      navigate('/verification', { replace: true })
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        const { fieldErrors, generalMessage } = mapApiValidationErrors(cause.payload)
        if (fieldErrors.date_of_birth) {
          setDobError(fieldErrors.date_of_birth)
        }
        setError(fieldErrors.date_of_birth || generalMessage || 'Please check your information and try again.')
      } else if (cause instanceof ApiError) {
        const msg = cause.message
        if (/failed \(422\)|HTTP 422|Unprocessable/i.test(msg)) {
          const { fieldErrors, generalMessage } = mapApiValidationErrors(cause.payload)
          if (fieldErrors.date_of_birth) setDobError(fieldErrors.date_of_birth)
          setError(fieldErrors.date_of_birth || generalMessage || 'Please check your information and try again.')
        } else {
          setError(msg)
        }
      } else {
        setError('Could not save your profile. Check your connection and try again.')
      }
    } finally { setBusy(false) }
  }

  if (profileLoading) return <main className="onboarding-flow"><p role="status">Loading your saved profile…</p></main>
  if (!user) return <Navigate to="/login" replace />
  if (profile && step !== 'profile') return <Navigate to="/verification" replace />
  if (!profile && step !== 'era' && !draft.era) return <Navigate to="/onboarding/era" replace />
  if (!profile && step === 'preferences' && !draft.vibe) return <Navigate to="/onboarding/situationship" replace />
  if (!profile && step === 'profile' && !draft.matchEra) return <Navigate to="/onboarding/preferences" replace />

  const isDobValid = Boolean(dob) && validateDateOfBirth(dob).valid

  return <main className="onboarding-flow" data-theme={selectedEra}>
    <div className="onboarding-flow-glow" />
    <header className="onboarding-flow-header"><Link to="/verification" aria-label="Back to verification">← Back</Link><span>{selectedTheme.emoji} {selectedTheme.name}</span></header>
    <div className="onboarding-flow-progress" aria-label={`Step ${stepIndex + 1} of 4`}>{[0,1,2,3].map(index => <span key={index} className={index <= stepIndex ? 'active' : ''} />)}</div>
    <section className="onboarding-flow-content">
      <p className="onboarding-flow-kicker">STEP {stepIndex + 1} OF 4</p>
      {step === 'era' && <>
        <h1>Pick your era, bestie <span className="e e-wiggle">👾</span></h1><p className="onboarding-flow-sub">Choose the energy that feels most like you.</p>
        <div className="onboarding-choice-grid fiu" role="radiogroup" aria-label="Pick your era">{(Object.keys(generationThemes) as GenerationId[]).map(id => {
          const theme = generationThemes[id]
          return <button
            type="button"
            role="radio"
            aria-checked={selectedEra === id}
            key={id}
            onClick={() => { updateDraft({ era: id }); setGeneration(id) }}
            className={`onboarding-choice era-choice interactive-tap ${selectedEra === id ? 'selected' : ''}`}
            data-era={id}
          >
            <span className="match-emoji-wrap-v3"><span className={`choice-emoji e ${theme.emojiAnimation}`}>{theme.emoji}</span></span>
            <span className="match-info-v3">
              <strong className="match-name-v3">{theme.name}</strong>
              <small className="match-desc-v3">{theme.eraDescription}</small>
              <span className="choice-tags">{theme.eraTags.join(' · ')}</span>
            </span>
            <span className="match-radio-v3" aria-hidden="true" />
          </button>
        })}</div>
        <button className="onboarding-flow-primary btn-cta" disabled={!draft.era && !profile?.era} onClick={() => next('situationship')}>Next <span className="btn-arrow">→</span></button>
      </>}
      {step === 'situationship' && <>
        <h1>{selectedTheme.vibeTitle} <span className={`e ${selectedTheme.vibeHeadingAnimation}`}>{selectedTheme.vibeHeadingEmoji}</span></h1><p className="onboarding-flow-sub">{selectedTheme.vibeSubtitle}</p>
        <div className="onboarding-choice-grid fiu" role="radiogroup" aria-label={selectedTheme.vibeTitle}>{selectedTheme.vibes.map(vibe => (
          <button
            type="button"
            role="radio"
            aria-checked={draft.vibe === vibe.name}
            key={vibe.name}
            onClick={() => updateDraft({ vibe: vibe.name })}
            className={`onboarding-choice vibe-choice interactive-tap ${draft.vibe === vibe.name ? 'selected' : ''}`}
          >
            <span className="match-emoji-wrap-v3"><span className={`choice-emoji e ${vibe.animation}`}>{vibe.icon}</span></span>
            <span className="match-info-v3">
              <strong className="match-name-v3">{vibe.name}</strong>
              <small className="match-desc-v3">{vibe.description}</small>
            </span>
            <span className="match-radio-v3" aria-hidden="true" />
          </button>
        ))}</div>
        <div className="onboarding-flow-actions"><button className="onboarding-flow-secondary" onClick={() => next('era')}>← Back</button><button className="onboarding-flow-primary btn-cta" disabled={!draft.vibe && !profile?.vibe_tag} onClick={() => next('preferences')}>Next <span className="btn-arrow">→</span></button></div>
      </>}
      {step === 'preferences' && <>
        <h1>{selectedTheme.matchTitle} <span className={`e match-era-heading-emoji ${selectedTheme.matchHeadingAnimation}`}>{selectedTheme.matchHeadingEmoji}</span></h1><p className="onboarding-flow-sub">Pick the era you want to match with.</p>
        <div className="match-grid-v3" role="radiogroup" aria-label="Choose the era you want to match with">
          {([
            { id: 'genz', emoji: '💀', animation: 'e-shake', name: 'Gen Z', description: 'TikTok-brained, chronically online' },
            { id: 'zillenial', emoji: '🎭', animation: 'e-flip', name: 'Zillenial', description: 'Gets both eras, chaos but self-aware' },
            { id: 'millennial', emoji: '✌️', animation: 'e-wave', name: 'Millennial', description: 'Emotionally available (mostly)' },
            { id: 'any', emoji: '🌈', animation: 'e-spin', name: 'Open to any era', description: "Love doesn't check a birth certificate" },
          ] as const).map(option => <button type="button" role="radio" aria-checked={draft.matchEra === option.id} key={option.id} onClick={() => updateDraft({ matchEra: option.id })} className={`match-card-v3 ${draft.matchEra === option.id ? 'selected' : ''}`} data-match={option.id}>
            <span className="match-emoji-wrap-v3"><span className={`e ${option.animation}`}>{option.emoji}</span></span><span className="match-info-v3"><strong className="match-name-v3">{option.name}</strong><small className="match-desc-v3">{option.description}</small></span><span className="match-radio-v3" aria-hidden="true" />
          </button>)}
        </div>
        <div className="onboarding-flow-actions"><button className="onboarding-flow-secondary" onClick={() => next('situationship')}>← Back</button><button className="onboarding-flow-primary match-era-cta btn-cta" disabled={!draft.matchEra} onClick={() => next('profile')}>Show me my matches <span className="btn-arrow">→</span></button></div>
      </>}
      {step === 'profile' && <>
        <h1>Complete your profile ✨</h1><p className="onboarding-flow-sub">A few details help us show you eligible people.</p>
        <form className="onboarding-profile-form" onSubmit={saveProfile}>
          <label>Display name<input required minLength={2} maxLength={80} value={fullName} onChange={e => setFullName(e.currentTarget.value)} autoComplete="name" /></label>
          <label>
            Date of birth
            <input
              required
              type="date"
              max={getMaxSelectableDob()}
              value={dob}
              onClick={e => {
                e.stopPropagation()
                try {
                  e.currentTarget.showPicker?.()
                } catch {
                  // Fallback if browser already opened picker or does not support showPicker
                }
              }}
              onChange={e => {
                const val = e.currentTarget.value
                setDob(val)
                if (!val) {
                  setDobError('')
                  if (error === dobError) setError('')
                  return
                }
                const check = validateDateOfBirth(val)
                if (!check.valid) {
                  setDobError(check.error!)
                  setError(check.error!)
                } else {
                  setDobError('')
                  if (
                    error === dobError ||
                    error === 'Please enter a valid date of birth.' ||
                    error === 'You must be at least 18 years old to use Raahi.' ||
                    error === 'Date of birth cannot be in the future.'
                  ) {
                    setError('')
                  }
                }
              }}
              onBlur={() => {
                if (dob) {
                  const check = validateDateOfBirth(dob)
                  if (!check.valid) {
                    setDobError(check.error!)
                  } else {
                    setDobError('')
                  }
                }
              }}
              aria-invalid={Boolean(dobError)}
              aria-describedby={dobError ? 'onboarding-dob-error' : undefined}
            />
            {dobError && (
              <span
                id="onboarding-dob-error"
                className="onboarding-field-error"
                role="alert"
                onClick={e => e.stopPropagation()}
              >
                {dobError}
              </span>
            )}
          </label>
          <label>Gender<select required value={gender} onChange={e => setGender(e.currentTarget.value as DatingGender)}><option value="prefer_not_to_say">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="nonbinary">Non-binary</option><option value="other">Other</option></select></label>
          <label>City<input required maxLength={60} value={city} onChange={e => setCity(e.currentTarget.value)} autoComplete="address-level2" /></label>
          <label>Bio<textarea maxLength={500} value={bio} onChange={e => setBio(e.currentTarget.value)} rows={3} /></label>
          <label>Who would you like to discover?<select value={targetGender} onChange={e => setTargetGender(e.currentTarget.value)}><option value="any">Everyone</option><option value="female">Women</option><option value="male">Men</option><option value="nonbinary">Non-binary people</option><option value="other">Other genders</option></select></label>
          <label>Preferred match era<select value={draft.matchEra ?? matchEra} onChange={e => updateDraft({ matchEra: e.currentTarget.value })}><option value="any">Open to any era</option><option value="genz">Gen Z</option><option value="zillenial">Zillenial</option><option value="millennial">Millennial</option></select></label>
          <label>Profile photos<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e => setPhotos(Array.from(e.currentTarget.files ?? []))} /></label>
          {photoProgress > 0 && <p role="status">Photo upload: {photoProgress}%</p>}
          <p className="onboarding-flow-privacy">Photos are saved to your profile and displayed to matches. You can customize your full interests, profession, and education on your Profile page.</p>
          {error && <p className="onboarding-flow-error" role="alert">{error}</p>}{success && <p role="status">{success}</p>}
          <div className="onboarding-flow-actions"><button type="button" className="onboarding-flow-secondary" onClick={() => next('preferences')}>← Back</button><button className="onboarding-flow-primary" disabled={busy || !isDobValid}>{busy ? 'Saving…' : 'Save & continue'}</button></div>
        </form>
      </>}
    </section>
  </main>
}
