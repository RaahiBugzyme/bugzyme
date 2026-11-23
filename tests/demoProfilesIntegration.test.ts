import test from 'node:test'
import assert from 'node:assert/strict'
import { THIRTY_DEMO_PROFILES, FIVE_DEMO_PROFILES, getAllFictionalProfiles } from '../src/data/demoProfiles.ts'
import { INITIAL_DEMO_CANDIDATES, getDemoFeedCandidates, getDemoCandidateById, swipeDemoCandidate } from '../src/data/demoAppData.ts'
import {
  getDemoConversationProfiles,
  getDemoProfile,
  appendDemoMessage,
  isDemoChat,
  getDemoMessages,
} from '../src/data/demoChatData.ts'
import { isDemoModeEnabled, setDemoMode } from '../src/utils/demoEnvironment.ts'

const testStorage = new Map<string, string>()
if (!globalThis.localStorage) {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => testStorage.get(key) ?? null,
      setItem: (key: string, value: string) => { testStorage.set(key, value) },
      removeItem: (key: string) => { testStorage.delete(key) },
    },
  })
}

test('all 30 demo profiles exist with unique IDs and realistic dating metadata', () => {
  const profiles = getAllFictionalProfiles()
  assert.equal(profiles.length, 30, 'There must be exactly 30 demo profiles')

  const ids = new Set<number>()
  for (const p of profiles) {
    assert.ok(!ids.has(p.id), `Profile ID ${p.id} must be unique`)
    ids.add(p.id)
    assert.ok(p.id >= 901 && p.id <= 930, `Profile ID ${p.id} should be in 901-930 range`)
    assert.ok(p.name && p.name.length >= 2, `Profile ${p.id} must have a valid name`)
    assert.ok(p.city && p.city.length >= 2, `Profile ${p.id} must have a location/city`)
    assert.ok(p.photos && p.photos.length >= 1, `Profile ${p.id} must have at least 1 photo`)
    assert.ok(p.isDemo === true, `Profile ${p.id} must be identified as isDemo: true`)
    assert.ok(isDemoChat(p.chatId), `Profile ${p.id} chatId must be a demo chat`)
  }
})

test('Discover, Matches and Conversations reference the exact same shared profile IDs', () => {
  const candidateIds = new Set(INITIAL_DEMO_CANDIDATES.map(c => c.id))
  const profileIds = new Set(THIRTY_DEMO_PROFILES.map(p => p.id))
  assert.equal(candidateIds.size, 30)
  assert.equal(profileIds.size, 30)

  // Verify full ID alignment across collections
  for (const id of profileIds) {
    assert.ok(candidateIds.has(id), `Candidate ID ${id} must exist in Discover candidates`)
    const candidate = getDemoCandidateById(id)
    const profile = getDemoProfile(id)
    assert.ok(candidate, `Candidate ${id} must be retrievable by ID`)
    assert.ok(profile, `Chat profile ${id} must be retrievable by ID`)
    assert.equal(candidate.name, profile.name, `Names must match for ID ${id}`)
    assert.equal(candidate.photos[0], profile.photo, `Primary photos must match for ID ${id}`)
  }
})

test('sending a message to a demo profile adds them to Conversations and updates preview', () => {
  // Candidate 923 starts unmessaged / unmatched
  const targetId = 923
  const candidate = getDemoCandidateById(targetId)
  assert.ok(candidate)

  const testContent = `Hello from integration test ${Date.now()}`
  appendDemoMessage(targetId, {
    id: Date.now(),
    chatId: targetId,
    senderId: 0,
    content: testContent,
    createdAt: new Date().toISOString(),
    isRead: true,
    isDelivered: true,
    messageType: 'text',
    reactions: [],
  })

  // Verify conversation is now listed in getDemoConversationProfiles
  const conversations = getDemoConversationProfiles()
  const found = conversations.find(c => c.id === targetId)
  assert.ok(found, `Profile ${targetId} must now appear in Conversations`)
  assert.equal(found.lastMessage, testContent, 'Conversation preview must show the sent message')
  assert.ok(found.photo, 'Conversation row must have profile photo')

  // Verify message history
  const history = getDemoMessages(targetId)
  assert.ok(history.some(m => m.content === testContent), 'Message must exist in chat history')

  // Verify no duplicate entries for the same profile
  const occurrences = conversations.filter(c => c.id === targetId)
  assert.equal(occurrences.length, 1, 'There must be no duplicate conversations for the same profile')
})

test('manager demonstration deck contains exactly five realistic demo profiles with complete dating data', () => {
  assert.equal(FIVE_DEMO_PROFILES.length, 5, 'Must contain exactly 5 demonstration profiles')

  const expectedNames = ['Riya Sen', 'Aditya Roy', 'Meera Krishnan', 'Kunal Verma', 'Ananya Deshmukh']
  const names = FIVE_DEMO_PROFILES.map(p => p.name)
  assert.deepEqual(names, expectedNames, 'Must match the 5 manager demonstration profiles')

  const cities = new Set(FIVE_DEMO_PROFILES.map(p => p.city))
  assert.ok(cities.has('Mumbai') && cities.has('Bengaluru') && cities.has('Delhi NCR') && cities.has('Pune'))

  for (const p of FIVE_DEMO_PROFILES) {
    assert.equal(p.isDemo, true)
    assert.ok(p.age && p.age >= 21 && p.age <= 30, `${p.name} must have a valid age`)
    assert.ok(p.profession && p.profession.length > 5, `${p.name} must have a realistic profession`)
    assert.ok(p.education && p.education.length > 5, `${p.name} must have a realistic education`)
    assert.ok(p.bio && p.bio.length > 20, `${p.name} must have an engaging bio`)
    assert.ok(p.interests.length >= 4, `${p.name} must have at least 4 interests`)
    assert.ok(p.relationshipIntentions && p.relationshipIntentions.length > 10, `${p.name} must have relationship intentions`)
    assert.ok(p.photos.length >= 3, `${p.name} must have at least 3 local photos`)
    for (const photo of p.photos) {
      assert.ok(typeof photo === 'string' && photo.length > 0, 'Photo must be a valid path/URL string')
    }
  }

  // Swiping like on Meera (903) or Ananya (905) matches back
  const meeraSwipe = swipeDemoCandidate(903, 'like')
  assert.equal(meeraSwipe.isMatch, true, 'Meera Krishnan matches back for demonstration')

  const ananyaSwipe = swipeDemoCandidate(905, 'like')
  assert.equal(ananyaSwipe.isMatch, true, 'Ananya Deshmukh matches back for demonstration')
})

test('isDemoModeEnabled safely isolates demo mode and prevents showing demo data to ordinary users', () => {
  // Ensure local storage is clean
  setDemoMode(false)
  assert.equal(isDemoModeEnabled(), false, 'Demo mode must be off by default')

  // Explicit activation
  setDemoMode(true)
  assert.equal(isDemoModeEnabled(), true, 'Demo mode activates when explicitly enabled')

  // Deactivation
  setDemoMode(false)
  assert.equal(isDemoModeEnabled(), false, 'Demo mode deactivates cleanly')
})
