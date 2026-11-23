import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import {
  getGoogleAuthUrl,
  submitGoogleCallback,
  loginWithGoogleCallback,
  sendPhoneOtp,
  verifyPhoneOtp,
  sendPasswordResetOtp,
  verifyPasswordResetOtp,
  sendPasswordResetLink,
  confirmPasswordResetLink,
} from '../src/api/auth.ts'

test('getGoogleAuthUrl calls /api/v1/auth/google/url with GET', async () => {
  const originalFetch = globalThis.fetch
  let observed: Request | undefined
  globalThis.fetch = async (input, init) => {
    observed = new Request(input, init)
    return Response.json({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=xyz', state: 'state123' })
  }
  try {
    const res = await getGoogleAuthUrl('https://raahi.app/auth/google/callback')
    assert.equal(res.state, 'state123')
    assert.match(res.authorization_url, /accounts\.google\.com/)
    assert.equal(new URL(observed?.url ?? '').pathname, '/api/v1/auth/google/url')
    assert.equal(new URL(observed?.url ?? '').searchParams.get('redirect_uri'), 'https://raahi.app/auth/google/callback')
    assert.equal(observed?.method, 'GET')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('submitGoogleCallback and loginWithGoogleCallback call /api/v1/auth/google/callback with POST', async () => {
  const originalFetch = globalThis.fetch
  let observed: Request | undefined
  globalThis.fetch = async (input, init) => {
    observed = new Request(input, init)
    return Response.json({
      access_token: 'google-jwt-token',
      token_type: 'bearer',
      is_new_user: false,
      user: { id: 1, email: 'googleuser@example.com', username: 'googleuser' }
    })
  }
  try {
    const res = await submitGoogleCallback({ code: 'test-code', state: 'test-state' })
    assert.equal(res.access_token, 'google-jwt-token')
    assert.equal(new URL(observed?.url ?? '').pathname, '/api/v1/auth/google/callback')
    assert.equal(observed?.method, 'POST')
    const body = await observed?.clone().json()
    assert.equal(body.code, 'test-code')
    assert.equal(body.state, 'test-state')

    // Test alias
    const res2 = await loginWithGoogleCallback({ code: 'test-code-2', state: 'test-state-2' })
    assert.equal(res2.access_token, 'google-jwt-token')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('sendPhoneOtp and verifyPhoneOtp call /api/v1/auth/phone endpoints with POST', async () => {
  const originalFetch = globalThis.fetch
  let observedUrls: string[] = []
  let observedBodies: any[] = []
  globalThis.fetch = async (input, init) => {
    const req = new Request(input, init)
    observedUrls.push(new URL(req.url).pathname)
    observedBodies.push(await req.json())
    if (new URL(req.url).pathname.endsWith('/send-otp')) {
      return Response.json({ message: 'OTP sent via SMS', success: true })
    }
    return Response.json({
      access_token: 'phone-jwt-token',
      token_type: 'bearer',
      is_new_user: true,
      user: { id: 2, phone_number: '+919876543210', username: 'phoneuser' }
    })
  }
  try {
    const sendRes = await sendPhoneOtp('+919876543210')
    assert.equal(sendRes.success, true)
    assert.equal(observedUrls[0], '/api/v1/auth/phone/send-otp')
    assert.equal(observedBodies[0].phone_number, '+919876543210')

    const verifyRes = await verifyPhoneOtp({
      phone_number: '+919876543210',
      otp: '123456',
      full_name: 'Test Phone User'
    })
    assert.equal(verifyRes.access_token, 'phone-jwt-token')
    assert.equal(verifyRes.is_new_user, true)
    assert.equal(observedUrls[1], '/api/v1/auth/phone/verify-otp')
    assert.equal(observedBodies[1].otp, '123456')
    assert.equal(observedBodies[1].full_name, 'Test Phone User')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('sendPasswordResetOtp and verifyPasswordResetOtp call /api/v1/auth/password-reset/ endpoints', async () => {
  const originalFetch = globalThis.fetch
  let observedUrls: string[] = []
  let observedBodies: any[] = []
  globalThis.fetch = async (input, init) => {
    const req = new Request(input, init)
    observedUrls.push(new URL(req.url).pathname)
    observedBodies.push(await req.json())
    return Response.json({ message: 'Success', success: true })
  }
  try {
    const sendRes = await sendPasswordResetOtp('user@example.com')
    assert.equal(sendRes.success, true)
    assert.equal(observedUrls[0], '/api/v1/auth/password-reset/send-otp')
    assert.equal(observedBodies[0].email, 'user@example.com')

    const verifyRes = await verifyPasswordResetOtp({
      email: 'user@example.com',
      otp: '654321',
      new_password: 'new-secure-password'
    })
    assert.equal(verifyRes.success, true)
    assert.equal(observedUrls[1], '/api/v1/auth/password-reset/verify-otp')
    assert.equal(observedBodies[1].otp, '654321')
    assert.equal(observedBodies[1].new_password, 'new-secure-password')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('sendPasswordResetLink and confirmPasswordResetLink call /api/v1/auth/password-reset/ link endpoints', async () => {
  const originalFetch = globalThis.fetch
  let observedUrls: string[] = []
  let observedBodies: any[] = []
  globalThis.fetch = async (input, init) => {
    const req = new Request(input, init)
    observedUrls.push(new URL(req.url).pathname)
    observedBodies.push(await req.json())
    return Response.json({ message: 'Success', success: true })
  }
  try {
    const sendRes = await sendPasswordResetLink('user@example.com')
    assert.equal(sendRes.success, true)
    assert.equal(observedUrls[0], '/api/v1/auth/password-reset/send-link')
    assert.equal(observedBodies[0].email, 'user@example.com')

    const confirmRes = await confirmPasswordResetLink({
      email: 'user@example.com',
      token: 'raw-token-123',
      new_password: 'new-secure-password-2'
    })
    assert.equal(confirmRes.success, true)
    assert.equal(observedUrls[1], '/api/v1/auth/password-reset/confirm-link')
    assert.equal(observedBodies[1].token, 'raw-token-123')
    assert.equal(observedBodies[1].new_password, 'new-secure-password-2')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Search route is removed from application navigation items and routes', () => {
  const layoutContent = fs.readFileSync(path.resolve('src/components/IntegrationLayout.tsx'), 'utf-8')
  assert.ok(!layoutContent.includes('to="/search"'), 'IntegrationLayout must not have to="/search" link')
  assert.ok(layoutContent.includes('to="/discover"'), 'IntegrationLayout must have to="/discover" link')
  assert.ok(layoutContent.includes('to="/matches"'), 'IntegrationLayout must have to="/matches" link')
  assert.ok(layoutContent.includes('to="/conversations"'), 'IntegrationLayout must have to="/conversations" link')
  assert.ok(layoutContent.includes('to="/profile"'), 'IntegrationLayout must have to="/profile" link')

  const appContent = fs.readFileSync(path.resolve('src/App.tsx'), 'utf-8')
  assert.ok(!appContent.includes('path="/search"'), 'App.tsx must not have /search route')
  assert.ok(appContent.includes('path="/forgot-password"'), 'App.tsx must have /forgot-password route')
  assert.ok(appContent.includes('path="/reset-password"'), 'App.tsx must have /reset-password route')
  assert.ok(appContent.includes('path="/auth/google/callback"'), 'App.tsx must have /auth/google/callback route')
})
