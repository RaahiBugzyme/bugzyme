import assert from 'node:assert/strict'
import test from 'node:test'
import { clearAuthToken, setAuthToken } from '../src/api/client.ts'
import { fetchFeed, searchProfiles, submitSwipe } from '../src/api/discover.ts'
import { getVerificationStatus, submitIdVerification } from '../src/api/verification.ts'

const storage = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) } })

test('Discover feed request uses the authenticated live feed API and pagination', async () => {
  const original = globalThis.fetch
  let request: Request | undefined
  setAuthToken('synthetic')
  globalThis.fetch = async (input, init) => { request = new Request(input, init); return Response.json({ profiles: [], total: 0, limit: 8, offset: 16, has_more: false }) }
  try {
    const feed = await fetchFeed(8, 16)
    assert.equal(new URL(request!.url).pathname, '/api/v1/feed')
    assert.equal(new URL(request!.url).search, '?limit=8&offset=16')
    assert.equal(request!.headers.get('authorization'), 'Bearer synthetic')
    assert.equal(feed.profiles.length, 0)
  } finally { globalThis.fetch = original; clearAuthToken() }
})

test('swipe maps super-like to the backend superlike action and uses target_user_id', async () => {
  const original = globalThis.fetch
  let request: Request | undefined
  globalThis.fetch = async (input, init) => { request = new Request(input, init); return Response.json({ id: 4, user_id: 2, target_user_id: 8, action: 'superlike', is_match: false }) }
  try {
    const result = await submitSwipe(8, 'superlike')
    assert.equal(new URL(request!.url).pathname, '/api/v1/swipe')
    assert.deepEqual(await request!.clone().json(), { target_user_id: 8, action: 'superlike' })
    assert.equal(result.is_match, false)
  } finally { globalThis.fetch = original }
})

test('verification state and ID evidence use the existing authenticated routes', async () => {
  const original = globalThis.fetch
  const originalXhr = globalThis.XMLHttpRequest
  const calls: Request[] = []
  let uploadUrl = ''
  let uploadBody: FormData | null = null
  class StubXHR {
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
    status = 201
    responseText = JSON.stringify({ verification_id: 10, verification_type: 'id_college', status: 'pending', submitted_at: '2026-01-01T00:00:00Z' })
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    open(_method: string, url: string) { uploadUrl = url }
    setRequestHeader() {}
    send(body: FormData) { uploadBody = body; this.onload?.() }
  }
  globalThis.XMLHttpRequest = StubXHR as unknown as typeof XMLHttpRequest
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init); calls.push(request)
    return request.method === 'GET'
      ? Response.json({ verifications: [], current_status: 'pending', is_face_verified: false, is_id_verified: false, verification_available: true })
      : Response.json({ verification_id: 10, verification_type: 'id_college', status: 'pending', submitted_at: '2026-01-01T00:00:00Z' }, { status: 201 })
  }
  try {
    assert.equal((await getVerificationStatus()).current_status, 'pending')
    await submitIdVerification('id_college', new File(['synthetic'], 'id.png', { type: 'image/png' }), () => {})
    assert.equal(new URL(calls[0].url).pathname, '/api/v1/verification/status')
    assert.equal(new URL(uploadUrl).pathname, '/api/v1/verification/id')
    assert.equal(uploadBody?.get('id_type'), 'id_college')
    assert.equal((uploadBody?.get('file') as File).name, 'id.png')
  } finally { globalThis.fetch = original; globalThis.XMLHttpRequest = originalXhr }
})

test('searchProfiles serializes query, interests, and filters to /api/v1/search', async () => {
  const original = globalThis.fetch
  let request: Request | undefined
  setAuthToken('synthetic-search-token')
  globalThis.fetch = async (input, init) => {
    request = new Request(input, init)
    return Response.json({
      results: [
        {
          user_id: 42,
          username: 'aarav_m',
          full_name: 'Aarav Mehta',
          age: 24,
          city: 'Mumbai',
          era: 'genz',
          vibe_tag: 'Coffee lover',
          bio: 'Exploring indie cafes and city sunsets',
          profession: 'Product Designer',
          education: 'NID Ahmedabad',
          relationship_intentions: 'Long-term relationship',
          interests: ['Coffee', 'Travel', 'Art'],
          photos: ['/uploads/profiles/aarav.jpg'],
          photo_url: '/uploads/profiles/aarav.jpg',
          is_verified: true,
          shared_interests: ['Coffee', 'Travel'],
          shared_interests_count: 2,
          relevance_score: 55.0,
        }
      ],
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false,
    })
  }

  try {
    const res = await searchProfiles({
      q: 'Aarav',
      city: 'Mumbai',
      profession: 'Designer',
      relationship_intentions: 'Long-term relationship',
      era: 'genz',
      min_age: 22,
      max_age: 30,
      interests: ['Coffee', 'Travel'],
      limit: 10,
      offset: 0,
    })

    const url = new URL(request!.url)
    assert.equal(url.pathname, '/api/v1/search')
    assert.equal(url.searchParams.get('q'), 'Aarav')
    assert.equal(url.searchParams.get('city'), 'Mumbai')
    assert.equal(url.searchParams.get('profession'), 'Designer')
    assert.equal(url.searchParams.get('relationship_intentions'), 'Long-term relationship')
    assert.equal(url.searchParams.get('era'), 'genz')
    assert.equal(url.searchParams.get('min_age'), '22')
    assert.equal(url.searchParams.get('max_age'), '30')
    assert.deepEqual(url.searchParams.getAll('interests'), ['Coffee', 'Travel'])
    assert.equal(request!.headers.get('authorization'), 'Bearer synthetic-search-token')

    assert.equal(res.total, 1)
    assert.equal(res.results[0].full_name, 'Aarav Mehta')
    assert.equal(res.results[0].shared_interests_count, 2)
  } finally {
    globalThis.fetch = original
    clearAuthToken()
  }
})
