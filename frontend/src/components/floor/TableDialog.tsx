import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Minus, Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { formatTimer } from '../../lib/format'
import { STATUS_STYLE } from '../../lib/status'
import { errorMessage } from '../../services/api'
import { restaurantService } from '../../services/restaurantService'
import type { FloorTable, TableActionName } from '../../types'
import { GradientButton, SoftButton } from '../ui/Buttons'
import { ErrorNote } from '../ui/Feedback'

interface TableDialogProps {
  restaurantId: number
  table: FloorTable
  now: number
  onClose: () => void
  onChanged: () => void
}

export function TableDialog({ restaurantId, table, now, onClose, onChanged }: TableDialogProps) {
  const [partySize, setPartySize] = useState(Math.min(2, table.seats))
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const action = useMutation({
    mutationFn: (name: TableActionName) =>
      restaurantService.tableAction(restaurantId, table.id, name, name === 'seat' ? partySize : undefined),
    onSuccess: () => {
      onChanged()
      onClose()
    },
  })

  const titleId = `table-${table.id}-title`

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-slate-950/50 p-4 sm:items-center" onClick={onClose}>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 id={titleId} className="text-xl font-bold">
              Table {table.label}
            </h2>
            <p className="mt-1 flex items-center gap-2 text-sm text-slate-700">
              <span className={`h-2.5 w-2.5 rounded-full ${STATUS_STYLE[table.status].dot}`} aria-hidden="true" />
              {STATUS_STYLE[table.status].label} · {table.seats} seats
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-slate-100"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        {table.status === 'occupied' && table.seated_at && (
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-slate-600">Seated for</dt>
              <dd className="font-mono text-lg font-semibold tabular-nums">{formatTimer(table.seated_at, now)}</dd>
            </div>
            <div>
              <dt className="text-slate-600">Guests</dt>
              <dd className="text-lg font-semibold">{table.party_size}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-slate-600">Waiter</dt>
              <dd className="font-medium">{table.first_served_at ? 'Has visited' : 'Not yet'}</dd>
            </div>
          </dl>
        )}

        {table.status === 'needs_cleaning' && table.vacated_at && (
          <p className="mt-4 text-sm text-slate-700">
            Guests left <span className="font-mono font-semibold tabular-nums">{formatTimer(table.vacated_at, now)}</span> ago.
          </p>
        )}

        <div className="mt-5 flex flex-col gap-2">
          {table.status === 'free' && (
            <>
              <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
                <span id={`${titleId}-party`} className="text-sm font-medium">
                  Party size
                </span>
                <div className="flex items-center gap-2" role="group" aria-labelledby={`${titleId}-party`}>
                  <SoftButton
                    aria-label="Fewer guests"
                    className="h-11 w-11 p-0"
                    disabled={partySize <= 1}
                    onClick={() => setPartySize((size) => size - 1)}
                  >
                    <Minus size={16} aria-hidden="true" />
                  </SoftButton>
                  <output className="w-6 text-center font-semibold">{partySize}</output>
                  <SoftButton
                    aria-label="More guests"
                    className="h-11 w-11 p-0"
                    disabled={partySize >= table.seats}
                    onClick={() => setPartySize((size) => size + 1)}
                  >
                    <Plus size={16} aria-hidden="true" />
                  </SoftButton>
                </div>
              </div>
              <GradientButton disabled={action.isPending} onClick={() => action.mutate('seat')}>
                Seat guests
              </GradientButton>
            </>
          )}
          {table.status === 'occupied' && (
            <>
              {!table.first_served_at && (
                <GradientButton disabled={action.isPending} onClick={() => action.mutate('served')}>
                  Waiter has visited
                </GradientButton>
              )}
              <SoftButton disabled={action.isPending} onClick={() => action.mutate('vacate')}>
                Guests have left
              </SoftButton>
            </>
          )}
          {table.status === 'needs_cleaning' && (
            <GradientButton disabled={action.isPending} onClick={() => action.mutate('cleaned')}>
              Mark as cleaned
            </GradientButton>
          )}
          {action.isError && <ErrorNote>{errorMessage(action.error)}</ErrorNote>}
        </div>
      </motion.div>
    </div>
  )
}
