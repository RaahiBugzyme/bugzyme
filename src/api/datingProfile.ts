import { ApiError, apiRequest, uploadForm } from './client.ts'

export type DatingEra = 'genz' | 'zillenial' | 'millennial'
export type DatingGender = 'male' | 'female' | 'nonbinary' | 'other' | 'prefer_not_to_say'

export interface ProfilePhoto {
  id: number
  photo_url: string
  is_primary: boolean
  display_order: number
}

export interface DatingProfile {
  id: number
  user_id: number
  full_name?: string | null
  bio?: string | null
  date_of_birth: string | null
  gender: DatingGender
  sexual_orientation: string | null
  sexual_orientation_consent?: boolean
  behavioral_personalization_enabled?: boolean
  city: string
  era: DatingEra
  vibe_tag: string | null
  profession?: string | null
  education?: string | null
  relationship_intentions?: string | null
  interests?: string[]
  photos?: ProfilePhoto[]
  target_gender_preference?: string
  match_era_preference: string
  is_face_verified: boolean
  is_id_verified: boolean
  verification_status: 'unverified' | 'pending' | 'verified' | 'rejected'
  created_at: string
  updated_at: string
}

export interface DatingProfileInput {
  date_of_birth?: string
  gender?: DatingGender
  city?: string
  era?: DatingEra
  vibe_tag?: string
  match_era_preference?: string
  target_gender_preference?: string
  profession?: string | null
  education?: string | null
  relationship_intentions?: string | null
  interests?: string[]
  full_name?: string | null
  bio?: string | null
}

export async function getMyDatingProfile(): Promise<DatingProfile | null> {
  try {
    return await apiRequest<DatingProfile>('/api/v1/profile/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function createDatingProfile(input: DatingProfileInput) {
  return apiRequest<DatingProfile>('/api/v1/profile', { method: 'POST', body: JSON.stringify(input) })
}

export function updateDatingProfile(input: Partial<DatingProfileInput>) {
  return apiRequest<DatingProfile>('/api/v1/profile/me', { method: 'PUT', body: JSON.stringify(input) })
}

export function uploadProfilePhoto(file: File, onProgress: (percentage: number) => void) {
  const form = new FormData()
  form.append('file', file)
  return uploadForm<ProfilePhoto>('/api/v1/profile/photos', form, onProgress)
}

export async function getMyProfilePhotos(): Promise<ProfilePhoto[]> {
  return apiRequest<ProfilePhoto[]>('/api/v1/profile/me/photos')
}

export function deleteProfilePhoto(photoId: number) {
  return apiRequest<{ deleted: boolean }>(`/api/v1/profile/photos/${photoId}`, { method: 'DELETE' })
}
