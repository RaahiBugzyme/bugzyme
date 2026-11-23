import { apiRequest, uploadForm } from './client.ts'

export interface VerificationRecord {
  id: number
  user_id: number
  verification_type: string
  status: 'pending' | 'passed' | 'failed' | 'cancelled'
  reviewed_at: string
}

export interface VerificationStatus {
  verifications: VerificationRecord[]
  current_status: 'unverified' | 'pending' | 'verified' | 'rejected' | null
  is_face_verified: boolean
  is_id_verified: boolean
  verification_available: boolean
}

export interface VerificationSubmission {
  verification_id: number
  verification_type: string
  status: 'pending'
  submitted_at: string
}

export function getVerificationStatus() {
  return apiRequest<VerificationStatus>('/api/v1/verification/status')
}

export function submitFaceVerification(file: File, onProgress: (percentage: number) => void) {
  const form = new FormData()
  form.append('file', file)
  return uploadForm<VerificationSubmission>('/api/v1/verification/face', form, onProgress)
}

export function submitIdVerification(
  idType: 'id_college' | 'id_work' | 'id_govt',
  file: File,
  onProgress: (percentage: number) => void,
) {
  const form = new FormData()
  form.append('id_type', idType)
  form.append('file', file)
  return uploadForm<VerificationSubmission>('/api/v1/verification/id', form, onProgress)
}
