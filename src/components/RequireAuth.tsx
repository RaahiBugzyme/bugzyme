import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { LoadingState } from './LoadingState'
import { useAuth } from '../state/AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState label="Checking your Raahi session…" />
  if (!user) {
    if (
      location.pathname.startsWith('/conversations') ||
      location.pathname.startsWith('/discover') ||
      location.pathname.startsWith('/matches') ||
      location.pathname.startsWith('/profile') ||
      location.pathname.startsWith('/settings') ||
      location.pathname.startsWith('/privacy') ||
      location.pathname.startsWith('/help')
    ) {
      return children
    }
    const next = `${location.pathname}${location.search}${location.hash}`
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace state={{ from: location }} />
  }
  return children
}
