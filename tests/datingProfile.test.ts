import assert from 'node:assert/strict'
import test from 'node:test'
import { createDatingProfile, getMyDatingProfile, updateDatingProfile, deleteProfilePhoto, type DatingProfile } from '../src/api/datingProfile.ts'
import { setAuthToken, clearAuthToken } from '../src/api/client.ts'
import { registerAccount } from '../src/api/accounts.ts'
import { postAuthenticationDestination } from '../src/routing/onboardingDestination.ts'

const values = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) },
})

const profile: DatingProfile = {
  id: 12, user_id: 7, date_of_birth: '1998-05-12', gender: 'female', sexual_orientation: null,
  city: 'Pune', era: 'zillenial', vibe_tag: 'Soft launch', match_era_preference: 'any',
  is_face_verified: false, is_id_verified: false, verification_status: 'unverified',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

test('profile lookup uses authenticated backend profile as the completion source', async () => {
  const originalFetch = globalThis.fetch
  setAuthToken('synthetic-jwt')
  let request: Request | undefined
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json(profile)
  }
  try {
    assert.deepEqual(await getMyDatingProfile(), profile)
    assert.equal(new URL(request!.url).pathname, '/api/v1/profile/me')
    assert.equal(request!.headers.get('authorization'), 'Bearer synthetic-jwt')
  } finally {
    globalThis.fetch = originalFetch
    clearAuthToken()
  }
})

test('profile lookup treats only backend 404 as incomplete onboarding', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => Response.json({ detail: 'Dating profile not found' }, { status: 404 })
  try {
    assert.equal(await getMyDatingProfile(), null)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('profile creation submits only the supported onboarding fields', async () => {
  const originalFetch = globalThis.fetch
  let request: Request | undefined
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json(profile, { status: 201 })
  }
  const input = { date_of_birth: '1998-05-12', gender: 'female' as const, city: 'Pune', era: 'zillenial' as const, vibe_tag: 'Soft launch', match_era_preference: 'millennial', target_gender_preference: 'female' }
  try {
    assert.deepEqual(await createDatingProfile(input), profile)
    assert.equal(new URL(request!.url).pathname, '/api/v1/profile')
    assert.equal(request!.method, 'POST')
    assert.deepEqual(await request!.clone().json(), input)
    const serialized = await request!.clone().json()
    assert.equal(serialized.match_era_preference, 'millennial')
    assert.equal(serialized.target_gender_preference, 'female')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('registration uses the existing backend account creation contract', async () => {
  const originalFetch = globalThis.fetch
  let request: Request | undefined
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json({ id: 7, username: 'raahi_user', full_name: null, email: 'user@example.test' }, { status: 201 })
  }
  try {
    assert.equal((await registerAccount({ username: 'raahi_user', email: 'user@example.test', password: 'secret123' })).id, 7)
    assert.equal(new URL(request!.url).pathname, '/register')
    assert.deepEqual(await request!.clone().json(), { username: 'raahi_user', email: 'user@example.test', password: 'secret123' })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('authenticated users without a profile resume onboarding; complete profile can enter with pending verification', () => {
  assert.equal(postAuthenticationDestination(null), '/onboarding/era')
  assert.equal(postAuthenticationDestination(profile), '/discover')
})

test('updateDatingProfile persists extended dating fields to PUT /api/v1/profile/me', async () => {
  const originalFetch = globalThis.fetch
  setAuthToken('synthetic-jwt')
  let request: Request | undefined
  const updatedResponse = {
    ...profile,
    profession: 'Architect',
    education: 'CEPT University',
    relationship_intentions: 'Long-term relationship',
    interests: ['Design', 'Pottery', 'Film'],
  }
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json(updatedResponse)
  }
  try {
    const input = {
      profession: 'Architect',
      education: 'CEPT University',
      relationship_intentions: 'Long-term relationship',
      interests: ['Design', 'Pottery', 'Film'],
    }
    const result = await updateDatingProfile(input)
    assert.deepEqual(result, updatedResponse)
    assert.equal(new URL(request!.url).pathname, '/api/v1/profile/me')
    assert.equal(request!.method, 'PUT')
    assert.deepEqual(await request!.clone().json(), input)
  } finally {
    globalThis.fetch = originalFetch
    clearAuthToken()
  }
})

test('deleteProfilePhoto sends DELETE request to /api/v1/profile/photos/:photoId', async () => {
  const originalFetch = globalThis.fetch
  setAuthToken('synthetic-jwt')
  let request: Request | undefined
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json({ deleted: true })
  }
  try {
    const result = await deleteProfilePhoto(42)
    assert.deepEqual(result, { deleted: true })
    assert.equal(new URL(request!.url).pathname, '/api/v1/profile/photos/42')
    assert.equal(request!.method, 'DELETE')
  } finally {
    globalThis.fetch = originalFetch
    clearAuthToken()
  }
})
