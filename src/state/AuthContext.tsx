import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiRequest, clearAuthToken, getAuthToken, setAuthToken } from '../api/client'

export interface CurrentUser {
  id: number
  username: string
  full_name: string | null
  bio: string | null
  email: string
  phone_number?: string | null
  auth_provider?: string
  ai_memory_enabled: boolean
  ai_provider_processing_enabled: boolean
  activity_status_enabled: boolean
}

interface AuthContextValue {
  user: CurrentUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithToken: (token: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  updateUser: (changes: Partial<Pick<CurrentUser, 'full_name' | 'bio' | 'ai_memory_enabled' | 'ai_provider_processing_enabled' | 'activity_status_enabled'>>) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    clearAuthToken()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    if (!getAuthToken()) {
      setUser(null)
      return
    }
    const current = await apiRequest<CurrentUser>('/me')
    setUser(current)
  }, [])

  useEffect(() => {
    let mounted = true
    const unauthorized = () => { if (mounted) logout() }
    window.addEventListener('raahi:unauthorized', unauthorized)
    void refreshUser().catch(() => { if (mounted) logout() }).finally(() => { if (mounted) setLoading(false) })
    return () => {
      mounted = false
      window.removeEventListener('raahi:unauthorized', unauthorized)
    }
  }, [logout, refreshUser])

  const login = useCallback(async (email: string, password: string) => {
    const form = new URLSearchParams({ username: email.trim(), password })
    const result = await apiRequest<{ access_token: string; token_type: string }>('/login', { method: 'POST', body: form })
    setAuthToken(result.access_token)
    try {
      const current = await apiRequest<CurrentUser>('/me')
      setUser(current)
    } catch (error) {
      clearAuthToken()
      throw error
    }
  }, [])

  const loginWithToken = useCallback(async (token: string) => {
    setAuthToken(token)
    try {
      const current = await apiRequest<CurrentUser>('/me')
      setUser(current)
    } catch (error) {
      clearAuthToken()
      throw error
    }
  }, [])

  const updateUser = useCallback(async (changes: Partial<Pick<CurrentUser, 'full_name' | 'bio' | 'ai_memory_enabled' | 'ai_provider_processing_enabled' | 'activity_status_enabled'>>) => {
    const current = await apiRequest<CurrentUser>('/me', { method: 'PATCH', body: JSON.stringify(changes) })
    setUser(current)
  }, [])

  const value = useMemo(() => ({ user, loading, login, loginWithToken, logout, refreshUser, updateUser }), [user, loading, login, loginWithToken, logout, refreshUser, updateUser])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
