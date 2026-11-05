import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../services/api'
import { restaurantService } from '../../services/restaurantService'
import type { FloorTable, TablePrediction, WaitlistEntry } from '../../types'
import { AnimatedInput } from '../ui/AnimatedInput'
import { GradientButton, SoftButton } from '../ui/Buttons'
import { ErrorNote } from '../ui/Feedback'
import { GlassCard } from '../ui/GlassCard'

interface WaitlistPanelProps {
  restaurantId: number
  waitlist: WaitlistEntry[]
  tables: FloorTable[]
  predictions: TablePrediction[]
  onChanged: () => void
}

export function WaitlistPanel({ restaurantId, waitlist, tables, predictions, onChanged }: WaitlistPanelProps) {
  const [name, setName] = useState('')
  const [partySize, setPartySize] = useState('2')

  const add = useMutation({
    mutationFn: () => restaurantService.addToWaitlist(restaurantId, name.trim(), Number(partySize)),
    onSuccess: () => {
      setName('')
      setPartySize('2')
      onChanged()
    },
  })
  const seat = useMutation({
    mutationFn: ({ entryId, tableId }: { entryId: number; tableId: number }) =>
      restaurantService.seatFromWaitlist(restaurantId, entryId, tableId),
    onSuccess: onChanged,
  })
  const leave = useMutation({
    mutationFn: (entryId: number) => restaurantService.leaveWaitlist(restaurantId, entryId),
    onSuccess: onChanged,
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    add.mutate()
  }

  const upcoming = predictions.filter((prediction) => prediction.status !== 'free').slice(0, 4)
  const usesHistory = predictions[0]?.based_on_history ?? false
  const error = add.error ?? seat.error ?? leave.error

  return (
    <GlassCard>
      <h2 className="font-semibold">Waitlist</h2>
      <form onSubmit={submit} className="mt-3 grid grid-cols-[1fr_5rem] gap-2">
        <AnimatedInput label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required />
        <AnimatedInput
          label="Guests"
          type="number"
          min={1}
          max={50}
          value={partySize}
          onChange={(e) => setPartySize(e.target.value)}
          required
        />
        <GradientButton type="submit" className="col-span-2" disabled={add.isPending}>
          Add to waitlist
        </GradientButton>
      </form>
      {error && (
        <div className="mt-2">
          <ErrorNote>{errorMessage(error)}</ErrorNote>
        </div>
      )}

      {waitlist.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2">
          {waitlist.map((entry) => {
            const suggested = tables.find((table) => table.id === entry.suggested_table_id)
            const canSeatNow = suggested?.status === 'free'
            return (
              <li key={entry.id} className="rounded-xl bg-slate-100 p-2.5 text-sm">
                <p className="font-semibold">
                  {entry.name} · {entry.party_size} {entry.party_size === 1 ? 'guest' : 'guests'}
                </p>
                <p className="text-slate-600">
                  {entry.suggested_table_label === null
                    ? 'No table is big enough or available yet'
                    : canSeatNow
                      ? `Table ${entry.suggested_table_label} is free now`
                      : `About ${entry.estimated_wait_minutes} min, table ${entry.suggested_table_label}`}
                </p>
                <div className="mt-2 flex gap-2">
                  {canSeatNow && suggested && (
                    <GradientButton
                      className="flex-1 px-3"
                      disabled={seat.isPending}
                      onClick={() => seat.mutate({ entryId: entry.id, tableId: suggested.id })}
                    >
                      Seat at {suggested.label}
                    </GradientButton>
                  )}
                  <SoftButton className="px-3" disabled={leave.isPending} onClick={() => leave.mutate(entry.id)}>
                    Remove
                  </SoftButton>
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {upcoming.length > 0 && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <h3 className="text-sm font-semibold">Likely free next</h3>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {upcoming.map((prediction) => (
              <li key={prediction.table_id} className="flex justify-between">
                <span>
                  Table {prediction.label} ({prediction.seats} seats)
                </span>
                <span className="font-medium">~{prediction.minutes_until_free} min</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-600">
            {usesHistory ? "Estimated from this restaurant's past turn times." : 'Estimated from your default turn time until more history builds up.'}
          </p>
        </div>
      )}
    </GlassCard>
  )
}
