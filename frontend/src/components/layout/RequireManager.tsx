import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useRestaurant } from '../../hooks/useRestaurant'

/** Sends staff back to the floor if they open a manager page directly. The server enforces this too. */
export function RequireManager({ children }: { children: ReactNode }) {
  const { floor } = useRestaurant()
  if (floor?.restaurant.my_role === 'staff') return <Navigate to="../floor" replace />
  return <>{children}</>
}
