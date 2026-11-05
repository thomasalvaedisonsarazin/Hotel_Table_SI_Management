import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { getAccessToken, liveUrl, refreshAccessToken } from '../services/api'
import { restaurantService } from '../services/restaurantService'
import type { AlertType, Floor, LiveMessage } from '../types'

const CLOSE_UNAUTHORIZED = 4401
const MAX_RETRY_MS = 30_000

export interface NewAlert {
  alertId: number
  tableId: number
  type: AlertType
}

export interface LiveFloor {
  floor: Floor | undefined
  isLoading: boolean
  isError: boolean
  connected: boolean
  newAlert: NewAlert | null
  dismissAlert: () => void
  refresh: () => void
}

export const floorKey = (id: number) => ['floor', id] as const

export function useLiveFloor(restaurantId: number): LiveFloor {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)
  const [newAlert, setNewAlert] = useState<NewAlert | null>(null)

  const query = useQuery({
    queryKey: floorKey(restaurantId),
    queryFn: () => restaurantService.floor(restaurantId),
    // Polling is the backstop: if the live connection drops, the board keeps updating.
    refetchInterval: connected ? 60_000 : 8_000,
    retry: (count, error) => {
      const status = (error as { response?: { status?: number } }).response?.status
      return status !== 404 && count < 2
    },
  })

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: floorKey(restaurantId) })
  }, [queryClient, restaurantId])

  useEffect(() => {
    let socket: WebSocket | null = null
    let stopped = false
    const retry = { attempts: 0 }
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      socket = new WebSocket(liveUrl(restaurantId))
      socket.onopen = () => socket?.send(JSON.stringify({ token: getAccessToken() }))
      socket.onmessage = (event: MessageEvent<string>) => {
        const message = JSON.parse(event.data) as LiveMessage
        if (message.type === 'ready') {
          retry.attempts = 0
          setConnected(true)
          refresh()
        } else if (message.type === 'floor_changed') {
          refresh()
        } else {
          setNewAlert({ alertId: message.alert_id, tableId: message.table_id, type: message.alert_type })
        }
      }
      socket.onclose = async (event) => {
        setConnected(false)
        if (stopped) return
        if (event.code === CLOSE_UNAUTHORIZED) await refreshAccessToken().catch(() => undefined)
        if (stopped) return
        retry.attempts += 1
        timer = setTimeout(connect, Math.min(1000 * 2 ** retry.attempts, MAX_RETRY_MS))
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      socket?.close()
    }
  }, [restaurantId, refresh])

  useEffect(() => {
    if (!newAlert) return
    const timer = setTimeout(() => setNewAlert(null), 8000)
    return () => clearTimeout(timer)
  }, [newAlert])

  return {
    floor: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    connected,
    newAlert,
    dismissAlert: () => setNewAlert(null),
    refresh,
  }
}
