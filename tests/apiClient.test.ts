import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError, apiRequest, AUTH_TOKEN_KEY, clearAuthToken, getAuthToken, resolveMediaUrl, setAuthToken, webSocketUrl } from '../src/api/client.ts'
import { deleteMessage, fetchChats, fetchMatches, fetchMessages, sendTextMessage } from '../src/api/chat.ts'

const storedValues = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key: string) => storedValues.get(key) ?? null,
    setItem: (key: string, value: string) => { storedValues.set(key, value) },
    removeItem: (key: string) => { storedValues.delete(key) },
  },
})

test('authenticated JSON requests attach the stored bearer token', async () => {
  setAuthToken('synthetic-jwt')
  const originalFetch = globalThis.fetch
  let observed: Request | undefined
  globalThis.fetch = async (input, init) => {
    observed = new Request(input, init)
    return Response.json([{ chat_id: 3 }])
  }
  try {
    const response = await apiRequest<{ chat_id: number }[]>('/chats')
    assert.equal(response[0].chat_id, 3)
    assert.equal(new Headers(observed?.headers).get('authorization'), 'Bearer synthetic-jwt')
    assert.equal(observed?.url, 'http://127.0.0.1:5257/chats')
  } finally {
    globalThis.fetch = originalFetch
    clearAuthToken()
  }
})

test('URL encoded login bodies retain form encoding instead of JSON encoding', async () => {
  const originalFetch = globalThis.fetch
  let observed: Request | undefined
  globalThis.fetch = async (input, init) => {
    observed = new Request(input, init)
    return Response.json({ access_token: 'synthetic', token_type: 'bearer' })
  }
  try {
    await apiRequest('/login', { method: 'POST', body: new URLSearchParams({ username: 'user@example.test', password: 'synthetic' }) })
    assert.equal(observed?.url, 'http://127.0.0.1:5257/login')
    assert.equal(new URL(observed?.url ?? '').pathname, '/login')
    assert.equal(observed?.method, 'POST')
    assert.match(observed?.headers.get('content-type') ?? '', /^application\/x-www-form-urlencoded/)
    assert.equal(await observed?.clone().text(), 'username=user%40example.test&password=synthetic')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('API errors retain status and show the backend detail message', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => Response.json({ detail: { code: 'ai_provider_unavailable', message: 'Try again soon.' } }, { status: 503 })
  try {
    await assert.rejects(apiRequest('/chats/9/coach'), (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.status, 503)
      assert.equal(error.message, 'Try again soon.')
      return true
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('network failures show an actionable backend connectivity message without leaking runtime details', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch at http://private-host/internal-stack') }
  try {
    await assert.rejects(apiRequest('/register'), (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.status, 0)
      assert.match(error.message, /could not reach its backend/i)
      assert.doesNotMatch(error.message, /private-host|internal-stack/i)
      return true
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('chat WebSocket URL carries the token using the backend query-token contract', () => {
  const url = new URL(webSocketUrl('/ws/27', 'jwt-with+symbols'))
  assert.equal(url.protocol, 'ws:')
  assert.equal(url.pathname, '/ws/27')
  assert.equal(url.searchParams.get('token'), 'jwt-with+symbols')
})

test('token storage is namespaced and clearable', () => {
  setAuthToken('temporary')
  assert.equal(getAuthToken(), 'temporary')
  assert.equal(AUTH_TOKEN_KEY, 'raahi.authToken.v1')
  clearAuthToken()
  assert.equal(getAuthToken(), null)
})

test('chat API wrappers use the existing backend paths and request schemas', async () => {
  const originalFetch = globalThis.fetch
  const seen: Request[] = []
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init)
    seen.push(request)
    if (request.url.includes('/api/v1/matches')) return Response.json({ matches: [], total: 0, limit: 50, offset: 0, has_more: false })
    if (request.url.endsWith('/chats')) return Response.json([])
    if (request.url.includes('/messages/4?')) return Response.json([])
    if (request.method === 'POST') return Response.json({ id: 19, chat_id: 4, content: 'Hi there.' })
    return Response.json({ ok: true, message_id: 19 })
  }
  try {
    assert.deepEqual((await fetchMatches()).matches, [])
    assert.deepEqual(await fetchChats(), [])
    assert.deepEqual(await fetchMessages(4, 200, 89), [])
    await sendTextMessage(4, 'Hi there.')
    await deleteMessage(19)
    assert.equal(new URL(seen[0].url).pathname, '/api/v1/matches')
    assert.equal(new URL(seen[1].url).pathname, '/chats')
    assert.equal(seen[2].url, 'http://127.0.0.1:5257/messages/4?limit=200&before_id=89')
    assert.equal(seen[3].url, 'http://127.0.0.1:5257/messages')
    assert.deepEqual(await seen[3].clone().json(), { chat_id: 4, content: 'Hi there.', reply_to_id: null })
    assert.equal(seen[4].url, 'http://127.0.0.1:5257/messages/19?for_everyone=true')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('resolveMediaUrl correctly formats backend relative paths, preserving external and data URLs', () => {
  assert.equal(resolveMediaUrl(''), '')
  assert.equal(resolveMediaUrl(null), '')
  assert.equal(resolveMediaUrl(undefined), '')
  assert.equal(resolveMediaUrl('/uploads/profiles/profile_123.jpg'), 'http://127.0.0.1:5257/uploads/profiles/profile_123.jpg')
  assert.equal(resolveMediaUrl('uploads/profiles/profile_123.jpg'), 'http://127.0.0.1:5257/uploads/profiles/profile_123.jpg')
  assert.equal(resolveMediaUrl('https://example.com/photo.jpg'), 'https://example.com/photo.jpg')
  assert.equal(resolveMediaUrl('http://example.com/photo.jpg'), 'http://example.com/photo.jpg')
  assert.equal(resolveMediaUrl('data:image/png;base64,abc'), 'data:image/png;base64,abc')
  assert.equal(resolveMediaUrl('blob:http://localhost:5173/uuid'), 'blob:http://localhost:5173/uuid')
})
