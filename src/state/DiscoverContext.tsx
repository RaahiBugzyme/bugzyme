import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Outlet } from 'react-router'
import { ApiError } from '../api/client'
import { fetchFeed, submitSwipe, type FeedProfile, type SwipeResponse } from '../api/discover'
import { useDatingProfile } from './DatingProfileContext'
import { useAuth } from './AuthContext'

export type DiscoverAction = SwipeResponse['action']
interface DiscoverContextValue {
  profiles: FeedProfile[]
  currentProfile: FeedProfile | null
  loading: boolean
  error: string | null
  actionError: string | null
  hasMore: boolean
  sessionLikes: number
  recordAction: (profile: FeedProfile, action: DiscoverAction) => Promise<boolean>
  loadMore: () => Promise<void>
  refresh: () => Promise<void>
}
const DiscoverContext = createContext<DiscoverContextValue | null>(null)

export function DiscoverProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { loading: profileLoading } = useDatingProfile()
  const [profiles, setProfiles] = useState<FeedProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [sessionLikes, setSessionLikes] = useState(0)

  const loadPage = useCallback(async (start: number, append: boolean) => {
    const page = await fetchFeed(20, start)
    setProfiles(current => append ? [...current, ...page.profiles] : page.profiles)
    setOffset(start + page.profiles.length)
    setHasMore(page.has_more)
    setError(null)
    return page.profiles.length
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      await loadPage(0, false)
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 403 ? cause.message : cause instanceof Error ? cause.message : 'Could not load Discover right now.')
      setProfiles([])
    } finally { setLoading(false) }
  }, [loadPage])

  useEffect(() => {
    if (!user || profileLoading) return
    void refresh()
  }, [user, profileLoading])

  const loadMore = useCallback(async () => {
    if (!hasMore || loading) return
    setLoading(true)
    try { await loadPage(offset, true) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load more profiles.') }
    finally { setLoading(false) }
  }, [hasMore, loading, loadPage, offset])

  const recordAction = useCallback(async (candidate: FeedProfile, action: DiscoverAction) => {
    setActionError(null)
    try {
      const response = await submitSwipe(candidate.user_id, action)
      setProfiles(current => current.filter(item => item.user_id !== candidate.user_id))
      if (action === 'like' || action === 'superlike') setSessionLikes(count => count + 1)
      if (response.is_match) window.dispatchEvent(new CustomEvent('raahi:real-match', { detail: { userId: candidate.user_id } }))
      return Boolean(response.is_match)
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Your action could not be saved. Please retry.')
      return false
    }
  }, [])

  const value = useMemo(() => ({ profiles, currentProfile: profiles[0] ?? null, loading, error, actionError, hasMore, sessionLikes, recordAction, loadMore, refresh }), [profiles, loading, error, actionError, hasMore, sessionLikes, recordAction, loadMore, refresh])
  return <DiscoverContext.Provider value={value}>{children}</DiscoverContext.Provider>
}
export function DiscoverRouteProvider() { return <DiscoverProvider><Outlet /></DiscoverProvider> }
export function useDiscover() {
  const value = useContext(DiscoverContext)
  if (!value) throw new Error('useDiscover must be used inside DiscoverProvider')
  return value
}
