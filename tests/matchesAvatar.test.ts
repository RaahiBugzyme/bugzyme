import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import type { ProfilePhoto, DatingProfile } from '../src/api/datingProfile.ts'

function getPrimaryPhotoUrl(photos?: ProfilePhoto[] | null): string | null {
  if (!photos || photos.length === 0) return null
  const primary = photos.find(p => p.is_primary)
  return (primary ?? photos[0])?.photo_url || null
}

function computeUserAvatarDisplay({
  user,
  profile,
  userPhotoFailed = false,
}: {
  user: { username: string; full_name?: string | null } | null
  profile: Partial<DatingProfile> | null
  userPhotoFailed?: boolean
}) {
  const photoUrl = getPrimaryPhotoUrl(profile?.photos)
  const initial = user?.username ? user.username[0]?.toUpperCase() : '😎'
  const shouldRenderPhoto = Boolean(photoUrl && !userPhotoFailed)

  return {
    photoUrl,
    shouldRenderPhoto,
    initial,
    renderSrc: shouldRenderPhoto ? photoUrl : null,
  }
}

test('getPrimaryPhotoUrl returns null when no photos exist', () => {
  assert.equal(getPrimaryPhotoUrl(null), null)
  assert.equal(getPrimaryPhotoUrl(undefined), null)
  assert.equal(getPrimaryPhotoUrl([]), null)
})

test('getPrimaryPhotoUrl returns photo when single photo exists', () => {
  const photos: ProfilePhoto[] = [
    { id: 1, photo_url: '/uploads/single.jpg', is_primary: false, display_order: 1 },
  ]
  assert.equal(getPrimaryPhotoUrl(photos), '/uploads/single.jpg')
})

test('getPrimaryPhotoUrl returns designated primary photo when multiple photos exist', () => {
  const photos: ProfilePhoto[] = [
    { id: 10, photo_url: '/uploads/photo1.jpg', is_primary: false, display_order: 1 },
    { id: 11, photo_url: '/uploads/primary-star.jpg', is_primary: true, display_order: 2 },
    { id: 12, photo_url: '/uploads/photo3.jpg', is_primary: false, display_order: 3 },
  ]
  assert.equal(getPrimaryPhotoUrl(photos), '/uploads/primary-star.jpg')
})

test('getPrimaryPhotoUrl falls back to first photo when multiple photos exist but none is marked primary', () => {
  const photos: ProfilePhoto[] = [
    { id: 21, photo_url: '/uploads/first.jpg', is_primary: false, display_order: 1 },
    { id: 22, photo_url: '/uploads/second.jpg', is_primary: false, display_order: 2 },
  ]
  assert.equal(getPrimaryPhotoUrl(photos), '/uploads/first.jpg')
})

test('Account WITH profile photo renders actual primary photo', () => {
  const user = { username: 'onkar_dev', full_name: 'Omkar Nagargoje' }
  const profileWithPhotos: Partial<DatingProfile> = {
    photos: [
      { id: 1, photo_url: '/uploads/side_view.jpg', is_primary: false, display_order: 1 },
      { id: 2, photo_url: '/uploads/main_portrait.jpg', is_primary: true, display_order: 2 },
    ],
  }

  const result = computeUserAvatarDisplay({ user, profile: profileWithPhotos, userPhotoFailed: false })
  assert.equal(result.shouldRenderPhoto, true)
  assert.equal(result.renderSrc, '/uploads/main_portrait.jpg')
})

test('Account WITHOUT profile photo renders initial fallback', () => {
  const user = { username: 'ananya99', full_name: 'Ananya Sharma' }
  const profileWithoutPhotos: Partial<DatingProfile> = {
    photos: [],
  }

  const result = computeUserAvatarDisplay({ user, profile: profileWithoutPhotos, userPhotoFailed: false })
  assert.equal(result.shouldRenderPhoto, false)
  assert.equal(result.renderSrc, null)
  assert.equal(result.initial, 'A')
})

test('Account WITH broken photo URL falls back to initial upon error', () => {
  const user = { username: 'rohit_k', full_name: 'Rohit Kumar' }
  const profileWithBrokenPhoto: Partial<DatingProfile> = {
    photos: [
      { id: 5, photo_url: '/uploads/broken-404.jpg', is_primary: true, display_order: 1 },
    ],
  }

  // Before error: attempts to render photo
  const beforeError = computeUserAvatarDisplay({ user, profile: profileWithBrokenPhoto, userPhotoFailed: false })
  assert.equal(beforeError.shouldRenderPhoto, true)
  assert.equal(beforeError.renderSrc, '/uploads/broken-404.jpg')

  // After image error event: falls back to initial
  const afterError = computeUserAvatarDisplay({ user, profile: profileWithBrokenPhoto, userPhotoFailed: true })
  assert.equal(afterError.shouldRenderPhoto, false)
  assert.equal(afterError.renderSrc, null)
  assert.equal(afterError.initial, 'R')
})

test('MatchesPages properly integrates logged-in user profile photo and resilient fallbacks', () => {
  const matchesPagesTsx = fs.readFileSync(path.resolve('src/pages/MatchesPages.tsx'), 'utf-8')

  // 1. Integrates useDatingProfile to get logged-in user's profile
  assert.ok(matchesPagesTsx.includes('useDatingProfile'), 'MatchesPages must import and use useDatingProfile')
  assert.ok(matchesPagesTsx.includes('getPrimaryPhotoUrl(profile?.photos)'), 'MatchesPage must select the primary photo from profile.photos')

  // 2. MatchCelebrationModal displays the user primary photo in celebration-avatar-ring
  assert.ok(matchesPagesTsx.includes('MatchCelebrationModal'), 'Must define MatchCelebrationModal')
  assert.ok(matchesPagesTsx.includes('userPrimaryPhoto && !userPhotoFailed'), 'Celebration modal must check userPrimaryPhoto and userPhotoFailed')
  assert.ok(matchesPagesTsx.includes('className="celebration-avatar-img"'), 'Celebration modal must use celebration-avatar-img class for photo')
  assert.ok(matchesPagesTsx.includes('onError={() => setUserPhotoFailed(true)}'), 'Must have onError fallback to user initial when image fails to load')

  // 3. MatchCelebrationModal preserves initial fallback when no photo exists or on failure
  assert.ok(matchesPagesTsx.includes('<span>{userInitial}</span>'), 'Must render userInitial fallback when photo is absent or fails to load')

  // 4. Preserves avatar sizes, styling and borders
  assert.ok(matchesPagesTsx.includes("className=\"celebration-avatar-ring\""), 'Must preserve celebration-avatar-ring class')
  assert.ok(matchesPagesTsx.includes("style={{ borderColor: 'var(--ep)', boxShadow: '0 0 24px rgba(216,61,180,0.5)', overflow: 'hidden' }}"), 'Must preserve celebration ring borders and shadows')

  // 5. MatchDetailPage passes photo to Avatar
  assert.ok(matchesPagesTsx.includes('<Avatar name={name} photo={photo} />'), 'MatchDetailPage must pass photo to Avatar')

  // 6. Avatar component supports onError fallback to initials
  assert.ok(matchesPagesTsx.includes('onError={() => setImgError(true)}'), 'Avatar component must have onError handler falling back to initials')

  // 7. ConversationPage partner avatar supports onError fallback
  assert.ok(matchesPagesTsx.includes('setPartnerPhotoError(true)'), 'ConversationPage must support onError fallback for partner avatar')
})
