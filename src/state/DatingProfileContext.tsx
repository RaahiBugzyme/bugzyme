import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getMyDatingProfile, type DatingProfile } from '../api/datingProfile'
import { useAuth } from './AuthContext'

interface DatingProfileContextValue {
  profile: DatingProfile | null
  loading: boolean
  error: string | null
  refreshProfile: () => Promise<DatingProfile | null>
  setProfile: (profile: DatingProfile | null) => void
}

const DatingProfileContext = createContext<DatingProfileContextValue | null>(null)

export function DatingProfileProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth()
  const [profile, setProfile] = useState<DatingProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refreshProfile = useCallback(async () => {
    if (!user) {
      setProfile(null)
      setError(null)
      return null
    }
    setLoading(true)
    setError(null)
    try {
      const current = await getMyDatingProfile()
      setProfile(current)
      return current
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Could not load your profile.'
      setError(message)
      throw cause
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    if (authLoading) return
    if (!user) {
      setProfile(null)
      setLoading(false)
      setError(null)
      return
    }
    void refreshProfile().catch(() => undefined)
  }, [authLoading, user, refreshProfile])

  const value = useMemo(() => ({ profile, loading: authLoading || loading, error, refreshProfile, setProfile }), [profile, authLoading, loading, error, refreshProfile])
  return <DatingProfileContext.Provider value={value}>{children}</DatingProfileContext.Provider>
}

export function useDatingProfile() {
  const value = useContext(DatingProfileContext)
  if (!value) throw new Error('useDatingProfile must be used inside DatingProfileProvider')
  return value
}
