import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertsPanel } from '../components/floor/AlertsPanel'
import { TableTile } from '../components/floor/TableTile'
import { TableDialog } from '../components/floor/TableDialog'
import { WaitlistPanel } from '../components/floor/WaitlistPanel'
import { PageWrapper } from '../components/layout/PageWrapper'
import { useRestaurant } from '../hooks/useRestaurant'
import { GradientButton } from '../components/ui/Buttons'
import { GlassCard } from '../components/ui/GlassCard'
import { useNow } from '../hooks/useNow'
import { cn } from '../lib/format'
import { STATUS_STYLE } from '../lib/status'
import type { Alert, TableStatus } from '../types'

const STATUSES: TableStatus[] = ['free', 'occupied', 'needs_cleaning']

export function FloorPage() {
  const { floor, connected, refresh, restaurantId } = useRestaurant()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const now = useNow(floor?.server_time)
  const closeDialog = useCallback(() => setSelectedId(null), [])

  const alertByTable = useMemo(() => {
    const map = new Map<number, Alert>()
    for (const alert of floor?.alerts ?? []) map.set(alert.table_id, alert)
    return map
  }, [floor?.alerts])

  if (!floor) return null
  const selected = floor.tables.find((table) => table.id === selectedId)
  const counts = STATUSES.map((status) => ({
    status,
    count: floor.tables.filter((table) => table.status === status).length,
  }))

  return (
    <PageWrapper>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold break-words">{floor.restaurant.name}</h1>
        <p className="flex items-center gap-2 text-sm text-slate-600" role="status">
          <span className={cn('h-2.5 w-2.5 rounded-full', connected ? 'bg-green-700' : 'bg-slate-400')} aria-hidden="true" />
          {connected ? 'Live' : 'Reconnecting, updating every few seconds'}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <GlassCard className="p-3 sm:p-5">
          <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {counts.map(({ status, count }) => (
              <li key={status} className="flex items-center gap-2">
                <span className={cn('h-3 w-3 rounded', STATUS_STYLE[status].dot)} aria-hidden="true" />
                {STATUS_STYLE[status].label}: <strong>{count}</strong>
              </li>
            ))}
          </ul>
          {floor.tables.length === 0 ? (
            <div className="py-16 text-center">
              <p className="mb-4 text-slate-600">No tables yet. Add them to your floor plan to get started.</p>
              <Link to="../setup">
                <GradientButton>Set up your floor</GradientButton>
              </Link>
            </div>
          ) : (
            <div className="relative h-[26rem] w-full rounded-xl bg-slate-100 sm:h-[34rem]">
              {floor.tables.map((table) => (
                <TableTile
                  key={table.id}
                  table={table}
                  alert={alertByTable.get(table.id)}
                  now={now}
                  onSelect={() => setSelectedId(table.id)}
                />
              ))}
            </div>
          )}
          {floor.tables.length > 0 && (
            <p className="mt-3 text-sm text-slate-600">Tap a table to seat guests or update it.</p>
          )}
        </GlassCard>

        <div className="flex flex-col gap-4">
          <AlertsPanel restaurantId={restaurantId} alerts={floor.alerts} now={now} onChanged={refresh} />
          <WaitlistPanel
            restaurantId={restaurantId}
            waitlist={floor.waitlist}
            tables={floor.tables}
            predictions={floor.predictions}
            onChanged={refresh}
          />
        </div>
      </div>

      {selected && (
        <TableDialog restaurantId={restaurantId} table={selected} now={now} onClose={closeDialog} onChanged={refresh} />
      )}
    </PageWrapper>
  )
}
