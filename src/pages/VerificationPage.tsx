import { useEffect, useMemo, useState, type ChangeEvent, type DragEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { getVerificationStatus, submitFaceVerification, submitIdVerification, type VerificationStatus } from '../api/verification'
import { LoadingState } from '../components/LoadingState'
import { useAuth } from '../state/AuthContext'
import { useDatingProfile } from '../state/DatingProfileContext'
import { isVerificationApproved } from '../routing/onboardingDestination'
import '../styles/onboarding-flow.css'
import '../styles/verification-v3.css'
import '../styles/verification-dev.css'

type IdType = 'id_college' | 'id_work' | 'id_govt'
const idOptions: Array<{ value: IdType; label: string; icon: string }> = [
  { value: 'id_college', label: 'College', icon: '🎓' },
  { value: 'id_work', label: 'Work', icon: '💼' },
  { value: 'id_govt', label: 'Govt ID', icon: '🏛️' },
]
const maxEvidenceSize = 10 * 1024 * 1024

export default function VerificationPage() {
  const navigate = useNavigate()
  const { user, loading: authLoading } = useAuth()
  const { profile, loading: profileLoading, error: profileError, refreshProfile } = useDatingProfile()
  const [status, setStatus] = useState<VerificationStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [faceFile, setFaceFile] = useState<File | null>(null)
  const [idFile, setIdFile] = useState<File | null>(null)
  const [faceFileError, setFaceFileError] = useState('')
  const [idFileError, setIdFileError] = useState('')
  const [idType, setIdType] = useState<IdType>('id_college')
  const [faceProgress, setFaceProgress] = useState(0)
  const [idProgress, setIdProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [uploadPendingReview, setUploadPendingReview] = useState(false)

  async function reloadStatus() {
    setStatusLoading(true)
    setStatusError('')
    try {
      const latestStatus = await getVerificationStatus()
      setStatus(latestStatus)
      if (latestStatus.current_status !== 'pending') setUploadPendingReview(false)
    }
    catch (cause) { setStatusError(cause instanceof Error ? cause.message : 'Could not load verification status.') }
    finally { setStatusLoading(false) }
  }
  useEffect(() => { if (user && profile) void reloadStatus() }, [user, profile?.id])
  const facePreview = useMemo(() => faceFile ? URL.createObjectURL(faceFile) : null, [faceFile])
  const idPreview = useMemo(() => idFile?.type.startsWith('image/') ? URL.createObjectURL(idFile) : null, [idFile])
  useEffect(() => () => { if (facePreview) URL.revokeObjectURL(facePreview) }, [facePreview])
  useEffect(() => () => { if (idPreview) URL.revokeObjectURL(idPreview) }, [idPreview])

  if (authLoading || profileLoading || statusLoading) return <main className="verification-v3-screen"><LoadingState label="Checking your verification status…" /></main>
  if (!user) return <Navigate to="/login?next=%2Fverification" replace />
  if (profileError) return <main className="onboarding-flow verification-v3-screen"><section className="verification-v3-content"><p className="step-label">Verification Required</p><h1 className="stitle">We couldn’t load your profile.</h1><p className="ssub" role="alert">{profileError}</p><button className="btn-cta" onClick={() => void refreshProfile().catch(() => undefined)}>Retry profile check</button></section></main>
  if (!profile) return <Navigate to="/onboarding/era" replace />
  if (isVerificationApproved(profile, status)) return <Navigate to="/discover" replace />

  const faceRecord = status?.verifications.find(record => record.verification_type === 'face')
  const idRecords = status?.verifications.filter(record => record.verification_type.startsWith('id_')) ?? []
  const idRecord = idRecords.find(record => record.verification_type === idType) ?? idRecords[0]
  const faceApproved = status?.is_face_verified === true && profile.is_face_verified
  const idApproved = status?.is_id_verified === true && profile.is_id_verified
  const approvedCount = Number(faceApproved) + Number(idApproved)
  const canUpload = status?.verification_available === true

  function acceptEvidence(file: File | null, kind: 'face' | 'id') {
    const setError = kind === 'face' ? setFaceFileError : setIdFileError
    const setFile = kind === 'face' ? setFaceFile : setIdFile
    setError(''); setUploadError('')
    if (!file) return
    const allowed = kind === 'face'
      ? ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)
      : ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(file.type)
    if (file.size > maxEvidenceSize) { setError('File must be 10 MB or smaller.'); return }
    if (!allowed) { setError(kind === 'face' ? 'Choose a JPEG, PNG or WEBP selfie.' : 'Choose a JPEG, PNG, WEBP image or PDF document.'); return }
    setFile(file)
    if (kind === 'face') setFaceProgress(0); else setIdProgress(0)
  }
  function acceptFile(event: ChangeEvent<HTMLInputElement>, kind: 'face' | 'id') {
    const file = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = ''
    acceptEvidence(file, kind)
  }
  function preventDrag(event: DragEvent<HTMLElement>) { event.preventDefault(); event.currentTarget.classList.add('drag-over') }
  function leaveDrag(event: DragEvent<HTMLElement>) { event.currentTarget.classList.remove('drag-over') }
  function droppedFile(event: DragEvent<HTMLLabelElement>, kind: 'face' | 'id') {
    event.preventDefault(); leaveDrag(event)
    acceptEvidence(event.dataTransfer.files[0] ?? null, kind)
  }
  async function submitEvidence() {
    if (!canUpload || (!faceFile && !idFile)) return
    setBusy(true); setUploadError('')
    try {
      if (faceFile) {
        const submission = await submitFaceVerification(faceFile, setFaceProgress)
        if (submission.status === 'pending') setUploadPendingReview(true)
      }
      if (idFile) {
        const submission = await submitIdVerification(idType, idFile, setIdProgress)
        if (submission.status === 'pending') setUploadPendingReview(true)
      }
      await reloadStatus()
      await refreshProfile()
      setFaceFile(null); setIdFile(null)
    } catch (cause) {
      setUploadError(cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : 'Could not submit evidence. Please try again.')
    } finally { setBusy(false) }
  }
  function reviewLabel(approved: boolean, record: VerificationStatus['verifications'][number] | undefined) {
    if (approved) return { className: 'approved', text: 'Approved by Raahi review' }
    if (record?.status === 'pending') return { className: 'pending', text: 'Pending review · not yet verified' }
    if (record?.status === 'failed') return { className: 'failed', text: 'Review was not approved · submit new evidence' }
    if (record?.status === 'cancelled') return { className: 'pending', text: 'Submission cancelled · choose a new file' }
    return { className: 'unsubmitted', text: 'Not submitted' }
  }
  const faceReview = reviewLabel(faceApproved, faceRecord)
  const idReview = reviewLabel(idApproved, idRecord)
  const pendingReview = status?.current_status === 'pending' || uploadPendingReview

  return <main className="onboarding-flow verification-v3-screen">
    <div className="onboarding-flow-glow" />
    <div className="step-row verification-v3-step-row"><span className="step-label">Verification Required</span><div className="step-dots" aria-label="Verification step"><span className="dot active" /><span className="dot" /><span className="dot" /><span className="dot" /></div></div>
    <section className="verification-v3-content">
      <h1 className="stitle fiu">Prove you're real,<br />not AI <span className="e e-wiggle">🛡️</span></h1>
      <p className="ssub fiu">Raahi only allows verified humans. <span className="e e-shake verification-inline-emoji">No catfishing</span>, no bots.</p>
      <div className="verify-progress fiu" role="progressbar" aria-label="Approved verification checks" aria-valuemin={0} aria-valuemax={2} aria-valuenow={approvedCount}><div className="verify-progress-fill" style={{ width: `${approvedCount * 50}%` }} /></div>
      {statusError && <div className="verification-api-error" role="alert"><span>{statusError}</span><button type="button" onClick={() => void reloadStatus()}>Retry status</button></div>}
      {status?.verification_available === false && <div className="verification-config-notice" role="status"><strong>Uploads are unavailable right now.</strong><span>The verification service reports that secure evidence storage or authorized reviewer configuration is incomplete. Your files have not been submitted.</span></div>}
      {pendingReview && <p className="verification-overall-pending" role="status">Your evidence is pending manual review. Uploading a file does not verify your account.</p>}
      {uploadError && <p className="verification-api-error" role="alert">{uploadError}</p>}
      <div className="verify-steps">
        <section className={`vstep fiu ${faceApproved ? 'done-step' : ''}`}>
          <div className="vstep-header"><div className="vstep-icon"><span className="e e-float">📸</span></div><div className="vstep-title">Clear Face Photo</div></div>
          <div className="vstep-sub">Upload a clear close-up selfie for private manual review.</div>
          <div className="vstep-body">
            <label className={`upload-zone ${faceFile ? 'has-file' : ''}`} onDragOver={preventDrag} onDragLeave={leaveDrag} onDrop={event => droppedFile(event, 'face')}>
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={event => acceptFile(event, 'face')} disabled={!canUpload || busy} aria-label="Choose face photo" />
              <span className="uz-icon e e-bounce">🤳</span><span className="uz-text">{faceFile ? <><strong>{faceFile.name}</strong><br />Ready to submit</> : <>Tap to upload · <strong>Selfie only</strong></>}</span>
              {facePreview && <img className="preview-img visible" src={facePreview} alt="Selected face photo preview" />}
            </label>
            {faceFileError && <p className="verification-file-error" role="alert">{faceFileError}</p>}
            {faceProgress > 0 && faceProgress < 100 && <div className="verification-upload-progress" role="status">Uploading face photo · {faceProgress}%</div>}
            <div className={`status-badge verification-record-status ${faceReview.className}`} role="status">{faceReview.text}</div>
          </div>
        </section>
        <section className={`vstep fiu ${idApproved ? 'done-step' : ''}`}>
          <div className="vstep-header"><div className="vstep-icon"><span className="e e-swing">🪪</span></div><div className="vstep-title">ID Verification</div></div>
          <div className="vstep-sub">College, Work or Government ID · submitted for private manual review.</div>
          <div className="vstep-body">
            <div className="id-type-row" role="group" aria-label="Choose ID type">{idOptions.map(option => <button key={option.value} type="button" className={`id-type-btn ${idType === option.value ? 'active' : ''}`} aria-pressed={idType === option.value} onClick={() => setIdType(option.value)} disabled={busy}><span className="e e-float">{option.icon}</span> {option.label}</button>)}</div>
            <label className={`upload-zone ${idFile ? 'has-file' : ''}`} onDragOver={preventDrag} onDragLeave={leaveDrag} onDrop={event => droppedFile(event, 'id')}>
              <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={event => acceptFile(event, 'id')} disabled={!canUpload || busy} aria-label="Choose identity document" />
              <span className="uz-icon e e-float">📄</span><span className="uz-text">{idFile ? <><strong>{idFile.name}</strong><br />{idOptions.find(option => option.value === idType)?.label} ID · Ready to submit</> : <>Tap to upload <strong>{idOptions.find(option => option.value === idType)?.label} ID</strong></>}</span>
              {idPreview && <img className="preview-img visible" src={idPreview} alt="Selected ID document preview" />}
            </label>
            {idFile && !idPreview && <p className="verification-file-name">{idFile.name}</p>}
            {idFileError && <p className="verification-file-error" role="alert">{idFileError}</p>}
            {idProgress > 0 && idProgress < 100 && <div className="verification-upload-progress" role="status">Uploading ID · {idProgress}%</div>}
            <div className={`status-badge verification-record-status ${idReview.className}`} role="status">{idReview.text}</div>
          </div>
        </section>
        <div className="privacy-note fiu"><span className="e e-shake verification-lock">🔒</span><strong> Privacy:</strong> Evidence is encrypted before private storage and accessible only through the authorized reviewer workflow. It is not shown on public profiles.</div>
      </div>
      <div className="verification-v3-cta-wrap"><button className="btn-cta" type="button" disabled={!canUpload || busy || (!faceFile && !idFile)} onClick={() => void submitEvidence()}>{busy ? 'Submitting for review…' : "I'm real, let me in"} <span className="btn-arrow">→</span></button><button className="verification-v3-refresh" type="button" disabled={busy || statusLoading} onClick={() => void reloadStatus()}>{statusLoading ? 'Refreshing…' : 'Refresh review status'}</button></div>
      <div className="verification-dev-continuation">
        <p>Verification stays pending until an authorized reviewer approves it. You can continue exploring Raahi now; verification-required actions will remain unavailable.</p>
        <button className="verification-dev-continue" type="button" onClick={() => navigate('/discover')}>Continue to Raahi <span aria-hidden="true">→</span></button>
      </div>
    </section>
  </main>
}
