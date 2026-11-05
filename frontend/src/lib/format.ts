import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]): string => twMerge(clsx(inputs))

export function formatTimer(fromIso: string, nowMs: number): string {
  const total = Math.max(0, Math.floor((nowMs - new Date(fromIso).getTime()) / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = String(total % 60).padStart(2, '0')
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}`
    : `${minutes}:${seconds}`
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} sec`
  return `${(seconds / 60).toFixed(1)} min`
}

export function formatHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function formatDateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

/**
 * Hours to show on a chart, in the order a restaurant's day runs. The axis starts after the
 * longest stretch with no guests, so a party staying past midnight lands at the end of the
 * evening instead of stretching the chart back to 00:00.
 */
export function businessHours(hours: number[]): number[] {
  const unique = [...new Set(hours)].sort((a, b) => a - b)
  if (unique.length === 0) return []
  let start = unique[0]
  let longestGap = -1
  unique.forEach((hour, index) => {
    const previous = unique[(index + unique.length - 1) % unique.length]
    const gap = (hour - previous + 24) % 24
    if (gap > longestGap) {
      longestGap = gap
      start = hour
    }
  })
  const span = 24 - longestGap + 1
  return Array.from({ length: unique.length === 1 ? 1 : span }, (_, i) => (start + i) % 24)
}
