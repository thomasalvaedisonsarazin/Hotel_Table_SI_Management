import { createContext } from 'react'
import type { User } from '../types'

export interface RegisterInput {
  email: string
  password: string
  full_name?: string
}

export interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
