import { apiRequest } from './client.ts'

export interface FeedProfile {
  user_id: number
  username: string
  full_name: string | null
  age: number | null
  city: string
  era: 'genz' | 'zillenial' | 'millennial'
  vibe_tag: string | null
  bio: string | null
  profession?: string | null
  education?: string | null
  relationship_intentions?: string | null
  interests?: string[]
  photos?: string[]
  photo_url?: string | null
  compatibility_score: number | null
  confidence_score: number | null
  adjusted_score: number | null
  recommendation_score: number | null
  score_type: 'profile_alignment' | null
  model_version: string | null
  prediction_provenance: string | null
  ranking_weights_validated: boolean
  matching_status: 'scored' | 'model_ineligible' | 'orientation_consent_required' | string
  is_face_verified: boolean
  is_id_verified: boolean
  verification_badge_required: boolean
}

export interface FeedResponse {
  profiles: FeedProfile[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface PublicProfile extends Omit<FeedProfile,
  'compatibility_score' | 'confidence_score' | 'adjusted_score' | 'recommendation_score' |
  'score_type' | 'model_version' | 'prediction_provenance' | 'ranking_weights_validated' |
  'matching_status' | 'is_face_verified' | 'is_id_verified' | 'verification_badge_required'
> {}

export interface SwipeResponse {
  id: number
  user_id: number
  target_user_id: number
  action: 'like' | 'pass' | 'superlike'
  created_at: string
  is_match?: boolean
}

export function fetchFeed(limit = 20, offset = 0) {
  return apiRequest<FeedResponse>(`/api/v1/feed?limit=${limit}&offset=${offset}`)
}

export function fetchPublicProfile(userId: number) {
  return apiRequest<PublicProfile>(`/api/v1/profile/${userId}`)
}

export function submitSwipe(targetUserId: number, action: SwipeResponse['action']) {
  return apiRequest<SwipeResponse>('/api/v1/swipe', {
    method: 'POST',
    body: JSON.stringify({ target_user_id: targetUserId, action }),
  })
}

export interface SearchCandidate {
  user_id: number
  username: string
  full_name: string | null
  age: number | null
  city: string | null
  era: string | null
  vibe_tag: string | null
  bio: string | null
  profession: string | null
  education: string | null
  relationship_intentions: string | null
  interests: string[]
  photos: string[]
  photo_url: string | null
  is_verified: boolean
  shared_interests: string[]
  shared_interests_count: number
  relevance_score: number
}

export interface SearchResponse {
  results: SearchCandidate[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface SearchParams {
  q?: string
  interests?: string[]
  city?: string
  profession?: string
  relationship_intentions?: string
  min_age?: number
  max_age?: number
  era?: string
  limit?: number
  offset?: number
}

export function searchProfiles(params: SearchParams = {}) {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.city) query.set('city', params.city)
  if (params.profession) query.set('profession', params.profession)
  if (params.relationship_intentions) query.set('relationship_intentions', params.relationship_intentions)
  if (params.min_age !== undefined) query.set('min_age', String(params.min_age))
  if (params.max_age !== undefined) query.set('max_age', String(params.max_age))
  if (params.era) query.set('era', params.era)
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))
  if (params.interests && params.interests.length > 0) {
    params.interests.forEach(interest => query.append('interests', interest))
  }
  const queryString = query.toString()
  return apiRequest<SearchResponse>(`/api/v1/search${queryString ? `?${queryString}` : ''}`)
}
