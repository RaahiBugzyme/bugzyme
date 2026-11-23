import type { DatingProfile } from '../api/datingProfile.ts'
import type { VerificationStatus } from '../api/verification.ts'
import { safeReturnPath } from './returnTo.ts'

export function isVerificationApproved(profile: DatingProfile | null, status: VerificationStatus | null) {
  return Boolean(
    profile
    && status
    && profile.is_face_verified
    && profile.is_id_verified
    && profile.verification_status === 'verified'
    && status.is_face_verified
    && status.is_id_verified
    && status.current_status === 'verified',
  )
}

export function postAuthenticationDestination(
  profile: DatingProfile | null,
  _verification: VerificationStatus | null = null,
  requestedPath: string | null = null,
) {
  if (!profile) return '/onboarding/era'
  if (!requestedPath) return '/discover'
  const safePath = safeReturnPath(requestedPath)
  return ['/login', '/register', '/', '/verification', '/onboarding', '/onboarding/era', '/onboarding/situationship', '/onboarding/preferences', '/onboarding/profile'].includes(safePath)
    ? '/discover'
    : safePath
}
