import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { Card } from '../components/Card'
import { Dialog } from '../components/Dialog'
import { generationThemes, type GenerationId } from '../data/generations'
import { matchEraOptions, type MatchEraId } from '../data/profiles'
import {
  blankProfileDraft,
  getProfileCompleteness,
  readDemoProfile,
  writeDemoProfile,
  type DemoProfileDraft,
  type DemoUserProfile,
} from '../data/userProfile'
import { useAuth } from '../state/AuthContext'
import { useDatingProfile } from '../state/DatingProfileContext'
import { useTheme } from '../state/ThemeContext'
import {
  updateDatingProfile,
  createDatingProfile,
  uploadProfilePhoto,
  deleteProfilePhoto,
  type DatingEra,
} from '../api/datingProfile'
import { resolveMediaUrl } from '../api/client'
import './profile.css'

const MAX_PHOTOS = 4
const MAX_PHOTO_BYTES = 10_000_000
const MAX_INTERESTS = 8

const POPULAR_INTERESTS = [
  'Indie Music 🎵',
  'Specialty Coffee ☕',
  'Film Photography 📸',
  'Night Drives 🚗',
  'Travel ✈️',
  'Boba Tea 🧋',
  'Vinyl Records 🎸',
  'Art Galleries 🎨',
  'Gym & Fitness 🏋️',
  'Anime & Manga 🍙',
]

type FieldErrors = Partial<Record<'name' | 'age' | 'city' | 'bio' | 'photos' | 'interests' | 'vibe' | 'lookingFor' | 'profession' | 'education' | 'relationshipIntentions', string>>

function calculateAge(dob: string | null | undefined): number {
  if (!dob) return 22
  const birth = new Date(dob)
  if (isNaN(birth.getTime())) return 22
  const today = new Date()
  let age = today.getFullYear() - birth.getFullYear()
  const m = today.getMonth() - birth.getMonth()
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) {
    age--
  }
  return age >= 18 ? age : 18
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => (typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Could not read this image.')))
    reader.onerror = () => reject(new Error('Could not read this image.'))
    reader.readAsDataURL(file)
  })
}

function generatePresetPortrait(name: string, era: GenerationId): string {
  const initial = name.trim()[0]?.toUpperCase() ?? '😎'
  const colors: Record<GenerationId, { border: string; bg: string; emoji: string }> = {
    genz: { border: '#a855f7', bg: '#2b0f4c', emoji: '💀' },
    zillenial: { border: '#f59e0b', bg: '#3d1b06', emoji: '🎭' },
    millennial: { border: '#06b6d4', bg: '#082f49', emoji: '⚡' },
  }
  const config = colors[era] || colors.genz
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500" width="100%" height="100%">
    <rect width="100%" height="100%" fill="${config.bg}"/>
    <circle cx="200" cy="220" r="100" fill="${config.border}" fill-opacity="0.25"/>
    <circle cx="200" cy="220" r="82" fill="#130826" stroke="${config.border}" stroke-width="4"/>
    <text x="200" y="250" font-family="'Syne', sans-serif" font-size="76" font-weight="800" fill="#ffffff" text-anchor="middle">${initial}</text>
    <circle cx="265" cy="285" r="28" fill="#1c0b36" stroke="${config.border}" stroke-width="2"/>
    <text x="265" y="296" font-size="28" text-anchor="middle">${config.emoji}</text>
  </svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function toDraft(profile: DemoUserProfile | null): DemoProfileDraft {
  if (!profile) return blankProfileDraft()
  return {
    name: profile.name,
    age: profile.age,
    city: profile.city,
    era: profile.era,
    bio: profile.bio,
    vibe: profile.vibe,
    lookingFor: profile.lookingFor,
    profession: profile.profession || '',
    education: profile.education || '',
    relationshipIntentions: profile.relationshipIntentions || 'long_term',
    interests: [...profile.interests],
    photos: [...profile.photos],
    photoIds: profile.photoIds ? [...profile.photoIds] : [],
  }
}

function validateDraft(draft: DemoProfileDraft): FieldErrors {
  const errors: FieldErrors = {}
  const name = draft.name.trim()
  if (name.length < 2 || name.length > 30) errors.name = 'Use a name between 2 and 30 characters.'
  if (!Number.isInteger(draft.age) || draft.age < 18 || draft.age > 99) errors.age = 'Age must be a whole number from 18 to 99.'
  if (draft.city.trim().length < 2 || draft.city.trim().length > 60) errors.city = 'Enter a city between 2 and 60 characters.'
  if (draft.bio.trim().length < 10 || draft.bio.trim().length > 300) errors.bio = 'Write 10–300 characters about yourself.'
  if (draft.photos.length === 0) errors.photos = 'Add at least one profile photo.'
  if (draft.photos.length > MAX_PHOTOS) errors.photos = `Add no more than ${MAX_PHOTOS} photos.`
  if (draft.interests.length < 2) errors.interests = 'Add at least 2 interests.'
  if (!draft.vibe) errors.vibe = 'Choose the vibe that fits you.'
  if (!draft.lookingFor) errors.lookingFor = 'Choose who you would like to meet.'
  return errors
}

export function ProfilePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { setGeneration } = useTheme()
  const { user, updateUser } = useAuth()
  const { profile: backendProfile, refreshProfile } = useDatingProfile()

  const [savedProfile, setSavedProfile] = useState<DemoUserProfile | null>(readDemoProfile)
  const [draft, setDraft] = useState<DemoProfileDraft>(() => toDraft(readDemoProfile()))
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formMessage, setFormMessage] = useState('')
  const [interestInput, setInterestInput] = useState('')
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [isPublicPreview, setIsPublicPreview] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const isEditing = location.pathname.endsWith('/create') || location.pathname.endsWith('/edit')
  const isCreating = location.pathname.endsWith('/create') || !savedProfile
  const completeness = useMemo(() => getProfileCompleteness(draft), [draft])
  const selectedTheme = generationThemes[draft.era] || generationThemes.genz

  function showToast(msg: string) {
    setToastMessage(msg)
    window.setTimeout(() => setToastMessage(null), 3000)
  }

  // Populate profile from backend data if authenticated
  useEffect(() => {
    if (user || backendProfile) {
      const fallback = readDemoProfile()
      const age = calculateAge(backendProfile?.date_of_birth)
      const name = user?.full_name || user?.username || fallback?.name || 'Raahi member'
      const city = backendProfile?.city || fallback?.city || 'Mumbai'
      const era = (backendProfile?.era || fallback?.era || 'genz') as GenerationId
      const bio = backendProfile?.bio ?? user?.bio ?? fallback?.bio ?? ''
      const vibe = backendProfile?.vibe_tag || fallback?.vibe || 'Low-key exclusive'
      const lookingFor = (backendProfile?.match_era_preference || fallback?.lookingFor || 'any') as MatchEraId
      const profession = backendProfile?.profession ?? fallback?.profession ?? ''
      const education = backendProfile?.education ?? fallback?.education ?? ''
      const relationshipIntentions = backendProfile?.relationship_intentions ?? fallback?.relationshipIntentions ?? 'long_term'
      const interests = backendProfile?.interests && backendProfile.interests.length > 0
        ? backendProfile.interests
        : (fallback?.interests ?? ['Indie Music', 'Night Walks', 'Coffee'])

      let photos: string[] = []
      let photoIds: number[] = []
      if (backendProfile?.photos && backendProfile.photos.length > 0) {
        photos = backendProfile.photos.map(p => p.photo_url)
        photoIds = backendProfile.photos.map(p => p.id)
      } else if (fallback?.photos && fallback.photos.length > 0) {
        photos = [...fallback.photos]
        photoIds = fallback.photoIds ? [...fallback.photoIds] : []
      }

      const merged: DemoUserProfile = {
        id: String(user?.id ?? fallback?.id ?? 'demo-user-1'),
        name,
        age,
        city,
        era,
        bio,
        vibe,
        lookingFor,
        profession,
        education,
        relationshipIntentions,
        interests,
        photos,
        photoIds,
        verificationStatus: (backendProfile?.verification_status || fallback?.verificationStatus || 'not_verified') as any,
        createdAt: backendProfile?.created_at || fallback?.createdAt || new Date().toISOString(),
        updatedAt: backendProfile?.updated_at || fallback?.updatedAt || new Date().toISOString(),
      }

      setSavedProfile(merged)
      setDraft(toDraft(merged))
    }
  }, [user, backendProfile])

  function updateField<K extends keyof DemoProfileDraft>(field: K, value: DemoProfileDraft[K]) {
    setDraft(previous => ({ ...previous, [field]: value }))
    setErrors(previous => ({ ...previous, [field]: undefined }))
  }

  function selectEra(event: ChangeEvent<HTMLSelectElement>) {
    const era = event.currentTarget.value as GenerationId
    updateField('era', era)
    updateField('vibe', generationThemes[era].vibes[0].name)
    setGeneration(era)
  }

  function addInterest(customValue?: string, event?: FormEvent) {
    event?.preventDefault()
    const value = (customValue || interestInput).trim().replace(/,+$/, '').slice(0, 24)
    if (!value) return
    if (draft.interests.some(interest => interest.toLowerCase() === value.toLowerCase())) {
      setFormMessage('That interest is already on your list.')
      return
    }
    if (draft.interests.length >= MAX_INTERESTS) {
      setFormMessage(`Keep your list to ${MAX_INTERESTS} interests.`)
      return
    }
    updateField('interests', [...draft.interests, value])
    setInterestInput('')
    setFormMessage('')
  }

  function removeInterest(value: string) {
    updateField('interests', draft.interests.filter(interest => interest !== value))
  }

  function addPresetPhoto() {
    if (draft.photos.length >= MAX_PHOTOS) {
      setErrors(previous => ({ ...previous, photos: `Your gallery can hold up to ${MAX_PHOTOS} photos.` }))
      return
    }
    const preset = generatePresetPortrait(draft.name || 'Raahi', draft.era)
    updateField('photos', [...draft.photos, preset])
    showToast('Added cosmic portrait! ✨')
  }

  async function addPhotos(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (!files.length) return
    setFormMessage('')
    if (files.some(file => !file.type.startsWith('image/'))) {
      setErrors(previous => ({ ...previous, photos: 'Choose image files only.' }))
      return
    }
    if (draft.photos.length + files.length > MAX_PHOTOS) {
      setErrors(previous => ({ ...previous, photos: `Your gallery can hold up to ${MAX_PHOTOS} photos.` }))
      return
    }
    if (files.some(file => file.size > MAX_PHOTO_BYTES)) {
      setErrors(previous => ({ ...previous, photos: 'Each image must be 10 MB or smaller.' }))
      return
    }

    if (user) {
      try {
        const newPhotos: string[] = []
        const newPhotoIds: number[] = []
        for (const file of files) {
          try {
            const uploaded = await uploadProfilePhoto(file, () => {})
            newPhotos.push(uploaded.photo_url)
            newPhotoIds.push(uploaded.id)
          } catch {
            const dataUrl = await fileToDataUrl(file)
            newPhotos.push(dataUrl)
          }
        }
        setDraft(prev => ({
          ...prev,
          photos: [...prev.photos, ...newPhotos],
          photoIds: [...(prev.photoIds || []), ...newPhotoIds],
        }))
        showToast('Photo uploaded successfully! 📸')
        void refreshProfile().catch(() => undefined)
        return
      } catch {
        setErrors(previous => ({ ...previous, photos: 'Could not upload photo. Try another file.' }))
        return
      }
    }

    try {
      const photos = await Promise.all(files.map(fileToDataUrl))
      updateField('photos', [...draft.photos, ...photos])
      showToast('Photo uploaded successfully! 📸')
    } catch {
      setErrors(previous => ({ ...previous, photos: 'Could not read one of those images. Try another file.' }))
    }
  }

  function removePhoto(index: number) {
    const photoId = draft.photoIds?.[index]
    if (photoId && user) {
      void deleteProfilePhoto(photoId).catch(() => undefined)
    }
    setDraft(prev => ({
      ...prev,
      photos: prev.photos.filter((_, photoIndex) => photoIndex !== index),
      photoIds: prev.photoIds ? prev.photoIds.filter((_, photoIndex) => photoIndex !== index) : [],
    }))
    setPreviewIndex(current => (current === index ? null : current !== null && current > index ? current - 1 : current))
  }

  function movePhoto(index: number, offset: -1 | 1) {
    const nextIndex = index + offset
    if (nextIndex < 0 || nextIndex >= draft.photos.length) return
    const photos = [...draft.photos]
    ;[photos[index], photos[nextIndex]] = [photos[nextIndex], photos[index]]
    const photoIds = draft.photoIds ? [...draft.photoIds] : undefined
    if (photoIds && photoIds[index] !== undefined && photoIds[nextIndex] !== undefined) {
      ;[photoIds[index], photoIds[nextIndex]] = [photoIds[nextIndex], photoIds[index]]
    }
    setDraft(prev => ({ ...prev, photos, photoIds: photoIds ?? prev.photoIds }))
  }

  function setAsPrimary(index: number) {
    if (index === 0 || index >= draft.photos.length) return
    const photos = [...draft.photos]
    const [selected] = photos.splice(index, 1)
    photos.unshift(selected)
    const photoIds = draft.photoIds ? [...draft.photoIds] : undefined
    if (photoIds && photoIds[index] !== undefined) {
      const [selectedId] = photoIds.splice(index, 1)
      photoIds.unshift(selectedId)
    }
    setDraft(prev => ({ ...prev, photos, photoIds: photoIds ?? prev.photoIds }))
    showToast('Updated primary photo! 🌟')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const validation = validateDraft(draft)
    setErrors(validation)
    setFormMessage('')
    if (Object.keys(validation).length) {
      const firstError = Object.keys(validation)[0]
      document.getElementById(`profile-${firstError}`)?.focus()
      return
    }

    setIsSaving(true)
    try {
      if (user) {
        await updateUser({
          full_name: draft.name.trim(),
          bio: draft.bio.trim(),
        })

        const datingPayload = {
          city: draft.city.trim(),
          era: draft.era as DatingEra,
          vibe_tag: draft.vibe,
          match_era_preference: draft.lookingFor,
          profession: draft.profession?.trim() || null,
          education: draft.education?.trim() || null,
          relationship_intentions: draft.relationshipIntentions || null,
          interests: draft.interests,
          full_name: draft.name.trim(),
          bio: draft.bio.trim(),
        }

        if (backendProfile) {
          await updateDatingProfile(datingPayload)
        } else {
          const today = new Date()
          const birthYear = today.getFullYear() - (draft.age || 20)
          const dob = `${birthYear}-01-01`
          await createDatingProfile({
            date_of_birth: dob,
            gender: 'prefer_not_to_say',
            city: draft.city.trim(),
            era: draft.era as DatingEra,
            vibe_tag: draft.vibe,
            match_era_preference: draft.lookingFor,
            target_gender_preference: 'any',
            profession: draft.profession?.trim() || null,
            education: draft.education?.trim() || null,
            relationship_intentions: draft.relationshipIntentions || null,
            interests: draft.interests,
            full_name: draft.name.trim(),
            bio: draft.bio.trim(),
          })
        }
        await refreshProfile()
      }

      const updated = writeDemoProfile(
        { ...draft, name: draft.name.trim(), city: draft.city.trim(), bio: draft.bio.trim() },
        savedProfile
      )
      if (updated) {
        setSavedProfile(updated)
      }
      showToast('Profile updated successfully! ✨')
      navigate('/profile', { replace: true })
    } catch (err) {
      setFormMessage(err instanceof Error ? err.message : 'Could not save profile. Please try again.')
    } finally {
      setIsSaving(false)
    }
  }

  function cancelEdit() {
    setDraft(toDraft(savedProfile))
    setErrors({})
    setFormMessage('')
    navigate('/profile')
  }

  const viewProfile = savedProfile ? toDraft(savedProfile) : draft

  // VIEW PROFILE MODE
  if (!isEditing) {
    return (
      <section className="profile-page page-enter">
        {toastMessage && <div className="discover-feedback-toast" role="status">{toastMessage}</div>}

        <div className="profile-heading-row fiu">
          <div>
            <p className="profile-eyebrow">RAAHI IDENTITY</p>
            <h1>Profile</h1>
          </div>
          <div className="profile-heading-actions">
            <button
              type="button"
              className="profile-button quiet"
              onClick={() => setIsPublicPreview(p => !p)}
            >
              {isPublicPreview ? 'Exit Preview' : 'Preview Public Card 👁'}
            </button>
            <button
              type="button"
              className="profile-button secondary"
              onClick={() => navigate('/profile/edit')}
            >
              ✏️ Edit profile
            </button>
            <Link to="/settings" className="profile-button secondary">
              <span aria-hidden="true">⚙</span> Settings
            </Link>
          </div>
        </div>

        <div className="profile-view-grid">
          {/* Main Profile Card */}
          <Card className="profile-view-card profile-person-card card-enter">
            {viewProfile.photos.length ? (
              <button
                type="button"
                className="profile-cover"
                onClick={() => setPreviewIndex(0)}
                aria-label="Open profile photo gallery"
              >
                <img src={resolveMediaUrl(viewProfile.photos[0])} alt={`${viewProfile.name}'s primary profile`} />
                <span className="profile-cover-count">
                  {viewProfile.photos.length} {viewProfile.photos.length === 1 ? 'photo' : 'photos'} · tap to view
                </span>
              </button>
            ) : (
              <div className="profile-cover profile-cover-empty">Add photos to complete your profile</div>
            )}

            <div className="profile-person-details">
              <div className="profile-name-row">
                <h2>
                  {viewProfile.name}, {viewProfile.age}
                </h2>
                <span
                  className="profile-era-pill"
                  style={{
                    color: selectedTheme.primary,
                    borderColor: selectedTheme.cardBorder,
                    background: selectedTheme.cardBackground,
                  }}
                >
                  <span className={`e ${selectedTheme.emojiAnimation}`}>{selectedTheme.emoji}</span>{' '}
                  {selectedTheme.name}
                </span>
              </div>

              <p className="profile-city">
                <span className="e e-float">📍</span> {viewProfile.city}
              </p>

              {(viewProfile.profession || viewProfile.education) && (
                <p className="profile-meta-sub" style={{ fontSize: '.88rem', color: 'rgba(235,230,250,0.85)', margin: '-10px 0 16px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {viewProfile.profession && <span>💼 {viewProfile.profession}</span>}
                  {viewProfile.profession && viewProfile.education && <span>·</span>}
                  {viewProfile.education && <span>🎓 {viewProfile.education}</span>}
                </p>
              )}

              <p className="profile-bio">{viewProfile.bio}</p>

              <div className="profile-tags">
                {viewProfile.interests.map(interest => (
                  <span className="profile-tag" key={interest}>
                    {interest}
                  </span>
                ))}
              </div>

              <div className="profile-preference-box">
                <span>Current vibe</span>
                <strong>{viewProfile.vibe}</strong>
                <span>Open to era</span>
                <strong>
                  {matchEraOptions.find(option => option.id === viewProfile.lookingFor)?.name ?? 'Open to any era'}
                </strong>
                {viewProfile.relationshipIntentions && (
                  <>
                    <span>Intentions</span>
                    <strong>{viewProfile.relationshipIntentions}</strong>
                  </>
                )}
              </div>
            </div>
          </Card>

          {/* Side Column: Photos grid & Completeness */}
          <aside className="profile-side-column">
            {/* Gallery Grid */}
            <Card className="profile-view-card card-enter">
              <div className="profile-section-title">
                <h2>Photo Gallery</h2>
                <span style={{ fontSize: '.8rem', color: 'rgba(255,255,255,.6)' }}>
                  {viewProfile.photos.length}/{MAX_PHOTOS}
                </span>
              </div>
              <div className="profile-photo-grid profile-gallery-grid">
                {viewProfile.photos.map((photo, idx) => (
                  <div
                    key={idx}
                    className="profile-photo-tile"
                    onClick={() => setPreviewIndex(idx)}
                    style={{ cursor: 'pointer', position: 'relative' }}
                    title="Tap to enlarge"
                  >
                    <img className="profile-gallery-thumb" src={resolveMediaUrl(photo)} alt={`Gallery view ${idx + 1}`} />
                    {idx === 0 && (
                      <span
                        style={{
                          position: 'absolute',
                          bottom: 4,
                          left: 4,
                          fontSize: '.62rem',
                          background: 'rgba(0,0,0,0.7)',
                          color: '#d8b4fe',
                          padding: '2px 6px',
                          borderRadius: 6,
                          fontWeight: 800,
                        }}
                      >
                        Primary ⭐
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            {/* Profile Completeness */}
            <Card className="profile-view-card profile-completeness-card card-enter">
              <div className="profile-section-title">
                <h2>Profile completeness</h2>
                <strong>{getProfileCompleteness(viewProfile)}%</strong>
              </div>
              <div
                className="profile-progress-track"
                role="progressbar"
                aria-label="Profile completeness"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={getProfileCompleteness(viewProfile)}
              >
                <span style={{ width: `${getProfileCompleteness(viewProfile)}%` }} />
              </div>
              <p>Complete your details, add interests, and upload photos to get 100% profile alignment.</p>
            </Card>

            {/* Quick Settings Link */}
            <Card className="profile-view-card card-enter">
              <div className="profile-section-title">
                <h2>Preferences & Settings</h2>
              </div>
              <p style={{ margin: '8px 0 16px', fontSize: '.82rem', color: 'rgba(255,255,255,.6)' }}>
                Configure dark mode, AI chat memory consent, in-app notifications, and privacy options.
              </p>
              <Link to="/settings" className="profile-button primary" style={{ width: '100%' }}>
                ⚙ Open Settings
              </Link>
            </Card>
          </aside>
        </div>

        {/* Lightbox Dialog */}
        <Dialog open={previewIndex !== null} title="Profile photo gallery" onClose={() => setPreviewIndex(null)}>
          {previewIndex !== null && viewProfile.photos[previewIndex] && (
            <div className="profile-gallery-viewer">
              <img src={resolveMediaUrl(viewProfile.photos[previewIndex])} alt={`${viewProfile.name}, photo ${previewIndex + 1}`} />
              <div className="profile-gallery-controls">
                <button
                  type="button"
                  className="profile-button secondary"
                  onClick={() => setPreviewIndex((previewIndex - 1 + viewProfile.photos.length) % viewProfile.photos.length)}
                  aria-label="Previous photo"
                >
                  ←
                </button>
                <span>
                  {previewIndex + 1} / {viewProfile.photos.length}
                </span>
                <button
                  type="button"
                  className="profile-button secondary"
                  onClick={() => setPreviewIndex((previewIndex + 1) % viewProfile.photos.length)}
                  aria-label="Next photo"
                >
                  →
                </button>
              </div>
            </div>
          )}
        </Dialog>
      </section>
    )
  }

  // EDIT PROFILE MODE
  return (
    <section className="profile-page profile-editor-page page-enter">
      {toastMessage && <div className="discover-feedback-toast" role="status">{toastMessage}</div>}

      <div className="profile-heading-row">
        <div>
          <p className="profile-eyebrow">{isCreating ? 'A little about you' : 'Make it feel like you'}</p>
          <h1>{isCreating ? 'Create your profile' : 'Edit profile'}</h1>
        </div>
        <button type="button" className="profile-button quiet" onClick={cancelEdit}>
          Cancel
        </button>
      </div>

      <Card className="profile-form-card">
        <form onSubmit={save} noValidate>
          {/* Section 1: Photos */}
          <div className="profile-form-section">
            <div className="profile-section-heading">
              <span>01</span>
              <div>
                <h2>Photos & Portraits</h2>
                <p>
                  Add up to {MAX_PHOTOS} photos. Your first image is shown as your primary card.
                </p>
              </div>
            </div>

            <div className="profile-photo-grid">
              {draft.photos.map((photo, index) => (
                <div
                  className={`profile-photo-tile${index === 0 ? ' cover' : ''}`}
                  key={`${photo.slice(0, 38)}-${index}`}
                >
                  <button
                    type="button"
                    className="profile-photo-preview"
                    onClick={() => setPreviewIndex(index)}
                    aria-label={`Preview photo ${index + 1}`}
                  >
                    <img src={resolveMediaUrl(photo)} alt={`Profile photo ${index + 1}`} />
                  </button>
                  <div className="profile-photo-actions">
                    {index === 0 ? (
                      <span className="profile-cover-label">Primary ⭐</span>
                    ) : (
                      <button type="button" onClick={() => setAsPrimary(index)}>
                        Make Primary
                      </button>
                    )}
                    <div style={{ display: 'flex', gap: 4 }}>
                      {index > 0 && (
                        <button type="button" onClick={() => movePhoto(index, -1)} title="Move left">
                          ◀
                        </button>
                      )}
                      {index < draft.photos.length - 1 && (
                        <button type="button" onClick={() => movePhoto(index, 1)} title="Move right">
                          ▶
                        </button>
                      )}
                      <button
                        type="button"
                        className="profile-remove-photo"
                        onClick={() => removePhoto(index)}
                        aria-label={`Remove photo ${index + 1}`}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </div>
              ))}

              {draft.photos.length < MAX_PHOTOS && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <label className="profile-photo-add">
                    <input
                      id="profile-photos"
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={addPhotos}
                      aria-describedby={errors.photos ? 'profile-photos-error' : undefined}
                    />
                    <span aria-hidden="true">＋</span>
                    <strong>Add photo</strong>
                    <small>
                      {draft.photos.length}/{MAX_PHOTOS}
                    </small>
                  </label>
                  <button
                    type="button"
                    className="profile-button quiet"
                    onClick={addPresetPhoto}
                    style={{ fontSize: '.72rem', minHeight: 34 }}
                  >
                    🎨 Add Preset Portrait
                  </button>
                </div>
              )}
            </div>
            {errors.photos && (
              <p className="profile-error" id="profile-photos-error" role="alert">
                {errors.photos}
              </p>
            )}
          </div>

          {/* Section 2: Personal Information */}
          <div className="profile-form-section">
            <div className="profile-section-heading">
              <span>02</span>
              <div>
                <h2>Personal information</h2>
                <p>The basics people see on your profile card.</p>
              </div>
            </div>

            <div className="profile-field-grid">
              <label className="profile-field" htmlFor="profile-name">
                <span>Display Name</span>
                <input
                  id="profile-name"
                  autoComplete="name"
                  maxLength={30}
                  value={draft.name}
                  onChange={event => updateField('name', event.currentTarget.value)}
                  placeholder="What should people call you?"
                  aria-invalid={Boolean(errors.name)}
                />
                {errors.name && <small className="profile-error">{errors.name}</small>}
              </label>

              <label className="profile-field" htmlFor="profile-age">
                <span>Age</span>
                <input
                  id="profile-age"
                  type="number"
                  min={18}
                  max={99}
                  step={1}
                  value={draft.age || ''}
                  onChange={event => updateField('age', Number(event.currentTarget.value))}
                  aria-invalid={Boolean(errors.age)}
                />
                {errors.age && <small className="profile-error">{errors.age}</small>}
              </label>

              <label className="profile-field" htmlFor="profile-city">
                <span>City</span>
                <input
                  id="profile-city"
                  autoComplete="address-level2"
                  maxLength={60}
                  value={draft.city}
                  onChange={event => updateField('city', event.currentTarget.value)}
                  placeholder="Mumbai, Delhi, Bengaluru…"
                  aria-invalid={Boolean(errors.city)}
                />
                {errors.city && <small className="profile-error">{errors.city}</small>}
              </label>

              <label className="profile-field" htmlFor="profile-era">
                <span>Your generation</span>
                <select id="profile-era" value={draft.era} onChange={selectEra}>
                  {Object.values(generationThemes).map(t => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="profile-field" htmlFor="profile-profession">
                <span>Profession / Occupation</span>
                <input
                  id="profile-profession"
                  maxLength={100}
                  value={draft.profession || ''}
                  onChange={event => updateField('profession', event.currentTarget.value)}
                  placeholder="Software Engineer, Designer, Student…"
                />
              </label>

              <label className="profile-field" htmlFor="profile-education">
                <span>Education / College</span>
                <input
                  id="profile-education"
                  maxLength={100}
                  value={draft.education || ''}
                  onChange={event => updateField('education', event.currentTarget.value)}
                  placeholder="IIT Bombay, Delhi University, High School…"
                />
              </label>

              <label className="profile-field profile-field-full" htmlFor="profile-relationship-intentions">
                <span>Relationship Intentions</span>
                <input
                  id="profile-relationship-intentions"
                  maxLength={60}
                  value={draft.relationshipIntentions || ''}
                  onChange={event => updateField('relationshipIntentions', event.currentTarget.value)}
                  placeholder="Long-term relationship, Casual dating, Figuring it out…"
                />
              </label>

              <label className="profile-field profile-field-full" htmlFor="profile-bio">
                <span>
                  About you <small>{draft.bio.length}/300</small>
                </span>
                <textarea
                  id="profile-bio"
                  rows={4}
                  maxLength={300}
                  value={draft.bio}
                  onChange={event => updateField('bio', event.currentTarget.value)}
                  placeholder="A few words about your vibe, your weekends, or your ideal date…"
                  aria-invalid={Boolean(errors.bio)}
                />
                {errors.bio && <small className="profile-error">{errors.bio}</small>}
              </label>
            </div>
          </div>

          {/* Section 3: Interests & Passions */}
          <div className="profile-form-section">
            <div className="profile-section-heading">
              <span>03</span>
              <div>
                <h2>Interests & Passions</h2>
                <p>Give matches easy conversation starters.</p>
              </div>
            </div>

            <div className="profile-interest-entry">
              <input
                id="profile-interests"
                value={interestInput}
                onChange={event => setInterestInput(event.currentTarget.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    addInterest()
                  }
                }}
                maxLength={24}
                placeholder="Type an interest..."
                aria-label="Add an interest"
                aria-invalid={Boolean(errors.interests)}
              />
              <button
                type="button"
                className="profile-button secondary"
                onClick={() => addInterest()}
                disabled={!interestInput.trim() || draft.interests.length >= MAX_INTERESTS}
              >
                Add
              </button>
            </div>

            {/* Popular quick-add suggestions */}
            <div style={{ margin: '10px 0 6px' }}>
              <span style={{ fontSize: '.74rem', color: 'rgba(255,255,255,.5)' }}>Popular suggestions:</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                {POPULAR_INTERESTS.filter(p => !draft.interests.includes(p)).map(p => (
                  <button
                    key={p}
                    type="button"
                    className="profile-tag"
                    onClick={() => addInterest(p)}
                    style={{ cursor: 'pointer', background: 'rgba(255,255,255,.04)' }}
                  >
                    ＋ {p}
                  </button>
                ))}
              </div>
            </div>

            <div className="profile-tags profile-edit-tags">
              {draft.interests.map(interest => (
                <span className="profile-tag" key={interest}>
                  {interest}
                  <button
                    type="button"
                    aria-label={`Remove ${interest}`}
                    onClick={() => removeInterest(interest)}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            {errors.interests && <p className="profile-error" role="alert">{errors.interests}</p>}
            {formMessage && <p className="profile-form-message" role="status">{formMessage}</p>}

            <div className="profile-field-grid preference-grid">
              <label className="profile-field" htmlFor="profile-vibe">
                <span>Current vibe</span>
                <select
                  id="profile-vibe"
                  value={draft.vibe}
                  onChange={event => updateField('vibe', event.currentTarget.value)}
                >
                  {selectedTheme.vibes.map(v => (
                    <option key={v.name} value={v.name}>
                      {v.name}
                    </option>
                  ))}
                </select>
                {errors.vibe && <small className="profile-error">{errors.vibe}</small>}
              </label>

              <label className="profile-field" htmlFor="profile-looking-for">
                <span>Who would you like to meet?</span>
                <select
                  id="profile-looking-for"
                  value={draft.lookingFor}
                  onChange={event => updateField('lookingFor', event.currentTarget.value as MatchEraId)}
                >
                  {matchEraOptions.map(option => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
                {errors.lookingFor && <small className="profile-error">{errors.lookingFor}</small>}
              </label>
            </div>
          </div>

          {/* Completeness Bar */}
          <div className="profile-completeness-preview">
            <div>
              <strong>{completeness}% complete</strong>
              <span>Changes are saved securely to your account.</span>
            </div>
            <div
              className="profile-progress-track"
              role="progressbar"
              aria-label="Draft profile completeness"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={completeness}
            >
              <span style={{ width: `${completeness}%` }} />
            </div>
          </div>

          <div className="profile-submit-row">
            <p>Your profile data and photos are saved securely to your Raahi account.</p>
            <div className="profile-submit-actions">
              <button type="button" className="profile-button quiet" onClick={cancelEdit} disabled={isSaving}>
                Cancel
              </button>
              <button type="submit" className="profile-button primary" disabled={isSaving}>
                {isSaving ? 'Saving…' : (isCreating ? 'Create profile' : 'Save changes')}
              </button>
            </div>
          </div>
        </form>
      </Card>

      <Dialog open={previewIndex !== null} title="Profile photo preview" onClose={() => setPreviewIndex(null)}>
        {previewIndex !== null && draft.photos[previewIndex] && (
          <img
            className="profile-editor-preview-image"
            src={resolveMediaUrl(draft.photos[previewIndex])}
            alt={`Profile photo ${previewIndex + 1} preview`}
          />
        )}
      </Dialog>
    </section>
  )
}
