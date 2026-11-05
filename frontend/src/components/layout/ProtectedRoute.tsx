import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { LoadingNote } from '../ui/Feedback'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <LoadingNote />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}
