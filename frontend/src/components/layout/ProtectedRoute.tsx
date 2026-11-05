import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { LoadingNote } from '../ui/Feedback'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()
  const { pathname } = useLocation()
  if (isLoading) return <LoadingNote />
  if (!user) return <Navigate to="/login" replace />
  if (user.must_change_password && pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }
  return <>{children}</>
}
