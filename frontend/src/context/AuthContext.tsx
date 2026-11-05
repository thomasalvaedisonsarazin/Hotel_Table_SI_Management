import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import api, { clearTokens, getAccessToken, getRefreshToken, storeTokens } from '../services/api'
import type { TokenPair, User } from '../types'
import { AuthContext, type AuthContextValue, type RegisterInput } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(() => getAccessToken() !== null)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!getAccessToken()) return
    api
      .get<User>('/auth/me')
      .then((response) => setUser(response.data))
      .catch(() => clearTokens())
      .finally(() => setIsLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password })
    const { data } = await api.post<TokenPair>('/auth/login', form)
    storeTokens(data)
    const me = await api.get<User>('/auth/me')
    setUser(me.data)
  }, [])

  const register = useCallback(
    async (input: RegisterInput) => {
      await api.post('/auth/register', input)
      await login(input.email, input.password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    const refresh = getRefreshToken()
    if (refresh) await api.post('/auth/logout', { refresh_token: refresh }).catch(() => undefined)
    clearTokens()
    queryClient.clear()
    setUser(null)
  }, [queryClient])

  const changePassword = useCallback(async (current: string, next: string) => {
    const { data } = await api.post<TokenPair>('/auth/change-password', {
      current_password: current,
      new_password: next,
    })
    storeTokens(data)
    const me = await api.get<User>('/auth/me')
    setUser(me.data)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, register, logout, changePassword }),
    [user, isLoading, login, register, logout, changePassword],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
