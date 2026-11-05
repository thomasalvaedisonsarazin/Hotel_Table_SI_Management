import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axios from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { TableTile } from '../components/floor/TableTile'
import { PeakHeatmap } from '../components/analytics/PeakHeatmap'
import { errorMessage, getAccessToken, refreshAccessToken, storeTokens } from '../services/api'
import { businessHours, formatSeconds, formatTimer } from '../lib/format'
import type { Alert, FloorTable } from '../types'

const NOW = new Date('2026-01-05T12:10:00Z').getTime()

const table = (overrides: Partial<FloorTable> = {}): FloorTable => ({
  id: 1,
  label: 'T1',
  seats: 4,
  x: 10,
  y: 10,
  status: 'free',
  status_changed_at: '2026-01-05T12:00:00Z',
  party_size: null,
  seated_at: null,
  first_served_at: null,
  vacated_at: null,
  session_source: null,
  ...overrides,
})

const waiterAlert: Alert = {
  id: 9,
  table_id: 1,
  table_label: 'T1',
  type: 'waiter',
  status: 'open',
  created_at: '2026-01-05T12:05:00Z',
  acknowledged_at: null,
  resolved_at: null,
}

describe('formatting', () => {
  it('formats timers', () => {
    expect(formatTimer('2026-01-05T12:05:09Z', NOW)).toBe('4:51')
    expect(formatTimer('2026-01-05T10:00:00Z', NOW)).toBe('2:10:00')
  })

  it('never shows a negative timer when clocks disagree', () => {
    expect(formatTimer('2026-01-05T12:10:30Z', NOW)).toBe('0:00')
  })

  it('formats durations', () => {
    expect(formatSeconds(null)).toBe('—')
    expect(formatSeconds(45)).toBe('45 sec')
    expect(formatSeconds(90)).toBe('1.5 min')
  })
})

describe('businessHours', () => {
  it('runs from opening time, with hours after midnight at the end', () => {
    expect(businessHours([0, 11, 12, 13, 22, 23])).toEqual([11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0])
  })

  it('keeps a normal day in order', () => {
    expect(businessHours([9, 10, 12])).toEqual([9, 10, 11, 12])
  })

  it('handles one hour and no hours', () => {
    expect(businessHours([20])).toEqual([20])
    expect(businessHours([])).toEqual([])
  })
})

describe('TableTile', () => {
  it('describes a free table in words, not only colour', () => {
    render(<TableTile table={table()} now={NOW} onSelect={() => undefined} />)
    expect(screen.getByRole('button', { name: 'Table T1, Free, 4 seats' })).toBeInTheDocument()
  })

  it('shows guests, timer and alert for an occupied table', async () => {
    const onSelect = vi.fn()
    render(
      <TableTile
        table={table({ status: 'occupied', party_size: 3, seated_at: '2026-01-05T12:00:00Z' })}
        alert={waiterAlert}
        now={NOW}
        onSelect={onSelect}
      />,
    )
    const tile = screen.getByRole('button', {
      name: 'Table T1, Occupied, 3 guests, waiting for a waiter',
    })
    expect(tile).toHaveTextContent('10:00')
    await userEvent.click(tile)
    expect(onSelect).toHaveBeenCalledOnce()
  })
})

describe('PeakHeatmap', () => {
  const cells = [
    { weekday: 4, hour: 20, avg_covers: 40, suggested_waiters: 2 },
    { weekday: 0, hour: 12, avg_covers: 10, suggested_waiters: 1 },
  ]

  it('labels every cell and switches metric', async () => {
    render(<PeakHeatmap cells={cells} />)
    const busy = screen.getByRole('button', {
      name: 'Fri 20:00: 40 guests on average, 2 waiters suggested',
    })
    expect(busy).toHaveTextContent('40')
    await userEvent.click(screen.getByRole('button', { name: 'Suggested waiters' }))
    expect(busy).toHaveTextContent('2')
  })

  it('offers a table view', async () => {
    render(<PeakHeatmap cells={cells} />)
    await userEvent.click(screen.getByRole('button', { name: 'View as table' }))
    expect(screen.getByRole('table')).toHaveTextContent('Fri')
  })
})

describe('auth token refresh', () => {
  it('shares one refresh between simultaneous callers', async () => {
    storeTokens({ access_token: 'old', refresh_token: 'refresh-1' })
    const post = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { access_token: 'new', refresh_token: 'refresh-2' } })

    const results = await Promise.all([refreshAccessToken(), refreshAccessToken(), refreshAccessToken()])

    expect(post).toHaveBeenCalledOnce()
    expect(results).toEqual(['new', 'new', 'new'])
    expect(getAccessToken()).toBe('new')
    post.mockRestore()
  })
})

describe('errorMessage', () => {
  it('falls back for unknown errors', () => {
    expect(errorMessage(new Error('boom'), 'fallback')).toBe('fallback')
  })
})
