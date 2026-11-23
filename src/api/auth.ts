import { apiRequest } from './client.ts'
import type { CurrentUser } from '../state/AuthContext'

export interface AuthTokenResult {
  access_token: string
  token_type: string
  user: CurrentUser
  is_new_user: boolean
}

export interface AuthMessageResult {
  message: string
  success: boolean
}

export interface GoogleAuthUrlResult {
  authorization_url: string
  state: string
}

// Google Authentication
export function getGoogleAuthUrl(redirectUri?: string) {
  const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : ''
  return apiRequest<GoogleAuthUrlResult>(`/api/v1/auth/google/url${query}`)
}

export function submitGoogleCallback(data: {
  code?: string
  code_verifier?: string
  state?: string
  id_token?: string
}) {
  return apiRequest<AuthTokenResult>('/api/v1/auth/google/callback', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export const loginWithGoogleCallback = submitGoogleCallback

// Phone Registration & SMS OTP
export function sendPhoneOtp(phoneNumber: string) {
  return apiRequest<AuthMessageResult>('/api/v1/auth/phone/send-otp', {
    method: 'POST',
    body: JSON.stringify({ phone_number: phoneNumber }),
  })
}

export function verifyPhoneOtp(data: {
  phone_number: string
  otp: string
  full_name?: string
  username?: string
}) {
  return apiRequest<AuthTokenResult>('/api/v1/auth/phone/verify-otp', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Password Recovery (OTP & Link)
export function sendPasswordResetOtp(email: string) {
  return apiRequest<AuthMessageResult>('/api/v1/auth/password-reset/send-otp', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function verifyPasswordResetOtp(data: {
  email: string
  otp: string
  new_password: string
}) {
  return apiRequest<AuthMessageResult>('/api/v1/auth/password-reset/verify-otp', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function sendPasswordResetLink(email: string) {
  return apiRequest<AuthMessageResult>('/api/v1/auth/password-reset/send-link', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function confirmPasswordResetLink(data: {
  token: string
  email: string
  new_password: string
}) {
  return apiRequest<AuthMessageResult>('/api/v1/auth/password-reset/confirm-link', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
