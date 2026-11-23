import type { GenerationId } from './generations.ts'
import { TWENTY_DEMO_PROFILES } from './demoProfiles.ts'

export interface DemoCandidate {
  id: number
  chatId: number
  name: string
  age: number
  gender?: 'female' | 'male' | 'non-binary' | null
  city: string
  era: GenerationId
  eraBadge: string
  eraIcon: string
  ringColor: string
  cornerEmoji: string
  vibeTag: string | null
  profession?: string | null
  education?: string | null
  bio: string | null
  tags: string[]
  relationshipIntentions?: string | null
  preferredAgeRange?: [number, number] | null
  preferredDistanceKm?: number | null
  preferredGenerations?: GenerationId[] | null
  completenessCategory?: string
  completenessScore?: number
  photos: string[]
  initials: string
  status: 'online' | 'offline'
  lastSeen: string
  isMatch: boolean
  lastMessage?: string
  lastMessageTime?: string
  unread?: boolean
  isNew?: boolean
  compatibilityScore?: number | null
}

export const INITIAL_DEMO_CANDIDATES: DemoCandidate[] = TWENTY_DEMO_PROFILES.map(p => ({
  id: p.id,
  chatId: p.chatId,
  name: p.name,
  age: p.age ?? 22,
  gender: p.gender,
  city: p.city,
  era: p.era,
  eraBadge: p.eraBadge,
  eraIcon: p.eraIcon,
  ringColor: p.ringColor,
  cornerEmoji: p.cornerEmoji,
  vibeTag: p.vibeTag,
  profession: p.profession,
  education: p.education,
  bio: p.bio,
  tags: p.interests,
  relationshipIntentions: p.relationshipIntentions,
  preferredAgeRange: p.preferredAgeRange,
  preferredDistanceKm: p.preferredDistanceKm,
  preferredGenerations: p.preferredGenerations,
  completenessCategory: p.completenessCategory,
  completenessScore: p.completenessScore,
  photos: p.photos,
  initials: p.initials,
  status: p.status,
  lastSeen: p.lastSeen,
  isMatch: p.isMatch,
  lastMessage: p.lastMessage,
  lastMessageTime: p.lastMessageTime,
  unread: p.unread,
  isNew: p.isNew,
  compatibilityScore: null,
}))

const DEMO_STATE_KEY = 'raahi_demo_app_state_v3'
const DEMO_BLOCKED_KEY = 'raahi_demo_blocked_users_v3'

interface DemoAppState {
  candidates: DemoCandidate[]
  swipedIds: Record<number, 'like' | 'pass' | 'superlike'>
  lastPassedId: number | null
}

function loadDemoAppState(): DemoAppState {
  try {
    const raw = localStorage.getItem(DEMO_STATE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as DemoAppState
      if (Array.isArray(parsed.candidates) && parsed.swipedIds) {
        if (parsed.candidates.length < INITIAL_DEMO_CANDIDATES.length) {
          const existingIds = new Set(parsed.candidates.map(c => c.id))
          const missing = INITIAL_DEMO_CANDIDATES.filter(c => !existingIds.has(c.id))
          parsed.candidates = [...parsed.candidates, ...missing]
          saveDemoAppState(parsed)
        }
        return parsed
      }
    }
  } catch {
    // fallback
  }
  const state: DemoAppState = {
    candidates: INITIAL_DEMO_CANDIDATES,
    swipedIds: {},
    lastPassedId: null,
  }
  saveDemoAppState(state)
  return state
}

function saveDemoAppState(state: DemoAppState) {
  try {
    localStorage.setItem(DEMO_STATE_KEY, JSON.stringify(state))
  } catch {
    // quota exceeded or private mode
  }
}

export function getDemoFeedCandidates(): DemoCandidate[] {
  const state = loadDemoAppState()
  return state.candidates.filter(c => !c.isMatch && !state.swipedIds[c.id])
}

export function swipeDemoCandidate(candidateId: number, action: 'like' | 'pass' | 'superlike'): { isMatch: boolean; candidate: DemoCandidate | null } {
  const state = loadDemoAppState()
  const candidate = state.candidates.find(c => c.id === candidateId) || null
  if (!candidate) return { isMatch: false, candidate: null }

  state.swipedIds[candidateId] = action

  if (action === 'pass') {
    state.lastPassedId = candidateId
    saveDemoAppState(state)
    return { isMatch: false, candidate }
  }

  // Like or Superlike: candidates with IDs 903, 905, 906, 908, 910, 911, 916, 918, 921, 924, 926, 930 match back, or any superlike!
  const isMutual =
    candidate.id === 903 ||
    candidate.id === 905 ||
    candidate.id === 906 ||
    candidate.id === 908 ||
    candidate.id === 910 ||
    candidate.id === 911 ||
    candidate.id === 916 ||
    candidate.id === 918 ||
    candidate.id === 921 ||
    candidate.id === 924 ||
    candidate.id === 926 ||
    candidate.id === 930 ||
    action === 'superlike'

  if (isMutual) {
    candidate.isMatch = true
    candidate.isNew = true
    candidate.unread = true
    candidate.lastMessage = action === 'superlike' ? 'Super liked you back! ⭐' : 'Matched with you! 🎉'
    candidate.lastMessageTime = 'Just now'
  }

  saveDemoAppState(state)
  return { isMatch: isMutual, candidate }
}

export function ensureDemoConversation(candidateId: number, lastMessage?: string): DemoCandidate | null {
  const state = loadDemoAppState()
  const candidate = state.candidates.find(c => c.id === candidateId)
  if (!candidate) return null
  candidate.isMatch = true
  if (lastMessage) {
    candidate.lastMessage = lastMessage
    candidate.lastMessageTime = 'Just now'
  }
  saveDemoAppState(state)
  return candidate
}

export function rewindLastPass(): DemoCandidate | null {
  const state = loadDemoAppState()
  if (!state.lastPassedId) return null
  const id = state.lastPassedId
  delete state.swipedIds[id]
  state.lastPassedId = null
  saveDemoAppState(state)
  return state.candidates.find(c => c.id === id) || null
}

export function hasLastPassedDemoCandidate(): boolean {
  const state = loadDemoAppState()
  return Boolean(state.lastPassedId)
}

export function getDemoMatches(): DemoCandidate[] {
  const state = loadDemoAppState()
  return state.candidates.filter(c => c.isMatch)
}

export function getDemoCandidateById(id: number): DemoCandidate | null {
  const state = loadDemoAppState()
  return state.candidates.find(c => c.id === id) || null
}

export function resetDemoFeed() {
  const state = loadDemoAppState()
  state.swipedIds = {}
  state.lastPassedId = null
  saveDemoAppState(state)
}

export function resetAllDemoData() {
  localStorage.removeItem(DEMO_STATE_KEY)
  localStorage.removeItem(DEMO_BLOCKED_KEY)
}

export function getBlockedUsers(): string[] {
  try {
    const raw = localStorage.getItem(DEMO_BLOCKED_KEY)
    if (raw) return JSON.parse(raw) as string[]
  } catch {
    // fallback
  }
  return ['spam_bot_01', 'offline_ghost_99']
}

export function unblockUser(username: string): string[] {
  const current = getBlockedUsers().filter(u => u !== username)
  try {
    localStorage.setItem(DEMO_BLOCKED_KEY, JSON.stringify(current))
  } catch {
    // fallback
  }
  return current
}

export function blockUser(username: string): string[] {
  const current = [...getBlockedUsers().filter(u => u !== username), username]
  try {
    localStorage.setItem(DEMO_BLOCKED_KEY, JSON.stringify(current))
  } catch {
    // fallback
  }
  return current
}
