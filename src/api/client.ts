export const AUTH_TOKEN_KEY = 'raahi.authToken.v1'

type ClientImportMeta = ImportMeta & {
  env?: {
    VITE_API_BASE_URL?: string
    DEV?: boolean
    PROD?: boolean
  }
}

const clientEnv = (import.meta as ClientImportMeta).env
const configuredApiBaseUrl = clientEnv?.VITE_API_BASE_URL?.trim()
const developmentApiBaseUrl = clientEnv?.DEV === true || clientEnv?.PROD !== true
  ? 'http://127.0.0.1:5257'
  : ''
const API_BASE_URL = (configuredApiBaseUrl || developmentApiBaseUrl).replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(status: number, message: string, payload: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

export function getAuthToken() {
  try {
    return globalThis.localStorage?.getItem(AUTH_TOKEN_KEY) ?? null
  } catch {
    return null
  }
}

export function setAuthToken(token: string) {
  try {
    globalThis.localStorage?.setItem(AUTH_TOKEN_KEY, token)
  } catch {
    // The current session can still authenticate if persistent storage is unavailable.
  }
}

export function clearAuthToken() {
  try {
    globalThis.localStorage?.removeItem(AUTH_TOKEN_KEY)
  } catch {
    // Keep logout usable when browser storage is disabled.
  }
}

export function apiUrl(path: string) {
  if (!API_BASE_URL) {
    throw new Error('VITE_API_BASE_URL must be configured for production.')
  }
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export function resolveMediaUrl(path: string | null | undefined): string {
  if (!path) return ''
  const trimmed = path.trim()
  if (!trimmed) return ''
  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('blob:')
  ) {
    return trimmed
  }
  return apiUrl(trimmed)
}

export function webSocketUrl(path: string, token: string) {
  const url = new URL(apiUrl(path))
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('token', token)
  return url.toString()
}

function notifyUnauthorized() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('raahi:unauthorized'))
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData
  const isUrlEncoded = typeof URLSearchParams !== 'undefined' && init.body instanceof URLSearchParams
  if (init.body && !isFormData && !isUrlEncoded && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let response: Response
  try {
    response = await fetch(apiUrl(path), { ...init, headers })
  } catch (error) {
    if (error instanceof TypeError) {
      const targetUrl = apiUrl(path)
      let destination: string
      try {
        const parsed = new URL(targetUrl)
        destination = `${parsed.protocol}//${parsed.host}${parsed.pathname}`
      } catch {
        destination = API_BASE_URL || 'configured address'
      }
      throw new ApiError(
        0,
        `Raahi could not reach its backend at ${destination}. Check that the backend is running on ${API_BASE_URL || 'the configured address'} and your connection is working.`,
        null
      )
    }
    throw error
  }
  if (response.status === 401) notifyUnauthorized()
  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => '')
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload
      ? (payload as { detail: unknown }).detail
      : payload
    const message = typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : Array.isArray(detail) && detail.length > 0
          ? detail
              .map(item => {
                if (typeof item === 'string') return item
                if (item && typeof item === 'object') {
                  const msg = 'msg' in item && typeof item.msg === 'string'
                    ? item.msg
                    : 'message' in item && typeof item.message === 'string'
                      ? item.message
                      : ''
                  return msg.replace(/^Value error,\s*/i, '')
                }
                return ''
              })
              .filter(Boolean)
              .join('. ') || (response.status === 422 ? 'Validation failed. Please check the entered information.' : `Request failed (${response.status})`)
          : response.status === 422
            ? 'Validation failed. Please check the entered information.'
            : `Request failed (${response.status})`
    throw new ApiError(response.status, message, payload)
  }
  return payload as T
}

export async function fetchProtectedBlob(path: string) {
  const headers = new Headers()
  const token = getAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(apiUrl(path), { headers })
  if (response.status === 401) notifyUnauthorized()
  if (!response.ok) throw new ApiError(response.status, `Download failed (${response.status})`, null)
  return { blob: await response.blob(), disposition: response.headers.get('content-disposition') }
}

export function uploadForm<T>(
  path: string,
  form: FormData,
  onProgress: (percentage: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', apiUrl(path))
    const token = getAuthToken()
    if (token) request.setRequestHeader('Authorization', `Bearer ${token}`)
    request.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () => reject(new ApiError(0, 'Upload network error', null))
    request.onabort = () => reject(new ApiError(0, 'Upload was cancelled', null))
    request.onload = () => {
      let payload: unknown = null
      try { payload = request.responseText ? JSON.parse(request.responseText) : null } catch { payload = request.responseText }
      if (request.status === 401) notifyUnauthorized()
      if (request.status < 200 || request.status >= 300) {
        const detail = payload && typeof payload === 'object' && 'detail' in payload
          ? (payload as { detail: unknown }).detail
          : payload
        reject(new ApiError(request.status, typeof detail === 'string' ? detail : `Upload failed (${request.status})`, payload))
        return
      }
      onProgress(100)
      resolve(payload as T)
    }
    request.send(form)
  })
}
