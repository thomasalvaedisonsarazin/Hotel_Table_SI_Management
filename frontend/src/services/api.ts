import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { TokenPair } from '../types'

const API_ROOT = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`

const ACCESS_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

export const getAccessToken = (): string | null => localStorage.getItem(ACCESS_KEY)

export const storeTokens = (tokens: TokenPair): void => {
  localStorage.setItem(ACCESS_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
}

export const getRefreshToken = (): string | null => localStorage.getItem(REFRESH_KEY)

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

const api = axios.create({ baseURL: API_ROOT })

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshInFlight: Promise<string> | null = null

/**
 * Refresh tokens rotate, and the server treats a reused one as theft and ends every session.
 * So requests that hit a 401 together must all share one refresh call.
 */
export function refreshAccessToken(): Promise<string> {
  refreshInFlight ??= axios
    .post<TokenPair>(`${API_ROOT}/auth/refresh`, { refresh_token: getRefreshToken() })
    .then(({ data }) => {
      storeTokens(data)
      return data.access_token
    })
    .finally(() => {
      refreshInFlight = null
    })
  return refreshInFlight
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const isAuthCall = config?.url?.startsWith('/auth/login') || config?.url?.startsWith('/auth/register')
    if (error.response?.status !== 401 || !config || config._retried || isAuthCall || !getRefreshToken()) {
      throw error
    }
    config._retried = true
    try {
      await refreshAccessToken()
    } catch {
      clearTokens()
      window.location.assign('/login')
      throw error
    }
    return api(config)
  },
)

export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
      return detail[0].msg.replace(/^Value error, /, '')
    }
    if (!error.response) return 'Cannot reach the server. Check your connection.'
  }
  return fallback
}

export function liveUrl(restaurantId: number): string {
  const base = import.meta.env.VITE_API_URL || window.location.origin
  const url = new URL(`/api/v1/ws/restaurants/${restaurantId}`, base)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export default api
