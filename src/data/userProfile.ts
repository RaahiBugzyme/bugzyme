import type { GenerationId } from './generations'
import type { MatchEraId } from './profiles'

export const USER_PROFILE_STORAGE_KEY = 'raahiDemoUserProfile.v1'

export interface DemoUserProfile {
  id: string
  name: string
  age: number
  city: string
  era: GenerationId
  bio: string
  vibe: string
  lookingFor: MatchEraId
  profession?: string | null
  education?: string | null
  relationshipIntentions?: string | null
  interests: string[]
  photos: string[]
  photoIds?: number[]
  verificationStatus: 'not_verified' | 'pending' | 'verified' | 'rejected'
  createdAt: string
  updatedAt: string
}

export type DemoProfileDraft = Omit<DemoUserProfile, 'id' | 'verificationStatus' | 'createdAt' | 'updatedAt'>

export function blankProfileDraft(): DemoProfileDraft {
  return {
    name: '', age: 18, city: '', era: 'genz', bio: '',
    vibe: 'Situationship', lookingFor: 'any',
    profession: '', education: '', relationshipIntentions: 'long_term',
    interests: [], photos: [], photoIds: [],
  }
}

function defaultDemoProfile(): DemoUserProfile {
  const dummyAvatar = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="100%" height="100%"><rect width="100%" height="100%" fill="%231a0a33"/><circle cx="200" cy="180" r="100" fill="%238b5cf6" fill-opacity="0.25"/><circle cx="200" cy="180" r="85" fill="%23120626" stroke="%23d83db4" stroke-width="4"/><text x="200" y="215" font-size="95" text-anchor="middle">😎</text></svg>`
  const now = new Date().toISOString()
  return {
    id: 'demo-user-1',
    name: 'onkarnagargoje12',
    age: 23,
    city: 'Mumbai',
    era: 'genz',
    bio: 'Just vibing, listening to indie playlists and looking for someone who doesn’t ghost 👻',
    vibe: 'Low-key exclusive',
    lookingFor: 'any',
    interests: ['Indie Music', 'Night Walks', 'Coffee', 'Film Photography'],
    photos: [dummyAvatar],
    verificationStatus: 'not_verified',
    createdAt: now,
    updatedAt: now,
  }
}

export function readDemoProfile(): DemoUserProfile | null {
  try {
    const raw = localStorage.getItem(USER_PROFILE_STORAGE_KEY)
    if (!raw) return defaultDemoProfile()
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object') return defaultDemoProfile()
    const profile = value as Partial<DemoUserProfile>
    if (
      typeof profile.id !== 'string' || typeof profile.name !== 'string' ||
      typeof profile.age !== 'number' || typeof profile.city !== 'string' ||
      typeof profile.bio !== 'string' || typeof profile.vibe !== 'string' ||
      !Array.isArray(profile.photos) || !Array.isArray(profile.interests) ||
      !['genz', 'zillenial', 'millennial'].includes(profile.era as string) ||
      !['genz', 'zillenial', 'millennial', 'any'].includes(profile.lookingFor as string)
    ) return defaultDemoProfile()
    return {
      ...profile,
      photos: profile.photos.filter((photo): photo is string => typeof photo === 'string' && photo.startsWith('data:image/')).slice(0, 4),
      interests: profile.interests.filter((interest): interest is string => typeof interest === 'string').slice(0, 8),
      verificationStatus: 'not_verified',
    } as DemoUserProfile
  } catch {
    return defaultDemoProfile()
  }
}

export function writeDemoProfile(draft: DemoProfileDraft, previous: DemoUserProfile | null): DemoUserProfile | null {
  const now = new Date().toISOString()
  const profile: DemoUserProfile = {
    ...draft,
    id: previous?.id ?? `demo-${Date.now().toString(36)}`,
    verificationStatus: 'not_verified',
    createdAt: previous?.createdAt ?? now,
    updatedAt: now,
  }
  try {
    localStorage.setItem(USER_PROFILE_STORAGE_KEY, JSON.stringify(profile))
    return profile
  } catch {
    return null
  }
}

export function getProfileCompleteness(profile: DemoProfileDraft): number {
  const checks = [
    profile.name.trim().length >= 2 && profile.age >= 18 && profile.city.trim().length >= 2,
    profile.bio.trim().length >= 20,
    profile.photos.length > 0,
    profile.interests.length >= 3,
    Boolean(profile.vibe),
    Boolean(profile.lookingFor),
  ]
  return Math.round(checks.filter(Boolean).length / checks.length * 100)
}
