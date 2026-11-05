import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Trash2 } from 'lucide-react'
import { useRef, useState, type FormEvent, type KeyboardEvent, type PointerEvent } from 'react'
import { PageWrapper } from '../components/layout/PageWrapper'
import { useRestaurant } from '../hooks/useRestaurant'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { GradientButton } from '../components/ui/Buttons'
import { ErrorNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { errorMessage } from '../services/api'
import { restaurantService } from '../services/restaurantService'
import type { FloorTable } from '../types'

const clamp = (value: number) => Math.min(92, Math.max(8, value))
const KEY_STEP = 2

interface Position {
  x: number
  y: number
}

/** First spot on a grid that no existing table is sitting on. */
function freeSpot(tables: FloorTable[]): Position {
  for (const y of [15, 40, 65, 88]) {
    for (const x of [12, 31, 50, 69, 88]) {
      if (!tables.some((table) => Math.abs(table.x - x) < 9 && Math.abs(table.y - y) < 12)) return { x, y }
    }
  }
  return { x: 50, y: 50 }
}

export function SetupPage() {
  const { floor, refresh, restaurantId } = useRestaurant()
  const [label, setLabel] = useState('')
  const [seats, setSeats] = useState('4')
  const [dragging, setDragging] = useState<{ id: number; position: Position } | null>(null)
  const mapRef = useRef<HTMLDivElement>(null)
  const tables = floor?.tables ?? []

  const add = useMutation({
    mutationFn: () =>
      restaurantService.addTable(restaurantId, { label: label.trim(), seats: Number(seats), ...freeSpot(tables) }),
    onSuccess: () => {
      setLabel('')
      refresh()
    },
  })
  const move = useMutation({
    mutationFn: ({ id, position }: { id: number; position: Position }) =>
      restaurantService.updateTable(restaurantId, id, position),
    onSettled: () => {
      setDragging(null)
      refresh()
    },
  })
  const update = useMutation({
    mutationFn: ({ id, ...data }: { id: number; label?: string; seats?: number }) =>
      restaurantService.updateTable(restaurantId, id, data),
    onSettled: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: number) => restaurantService.removeTable(restaurantId, id),
    onSettled: refresh,
  })

  const positionFromPointer = (event: PointerEvent): Position | null => {
    const box = mapRef.current?.getBoundingClientRect()
    if (!box) return null
    return {
      x: clamp(((event.clientX - box.left) / box.width) * 100),
      y: clamp(((event.clientY - box.top) / box.height) * 100),
    }
  }

  const onPointerMove = (event: PointerEvent, id: number) => {
    if (dragging?.id !== id) return
    const position = positionFromPointer(event)
    if (position) setDragging({ id, position })
  }

  const onPointerUp = (id: number) => {
    if (dragging?.id === id) move.mutate(dragging)
  }

  const onKeyDown = (event: KeyboardEvent, table: FloorTable) => {
    const delta: Record<string, Position> = {
      ArrowLeft: { x: -KEY_STEP, y: 0 },
      ArrowRight: { x: KEY_STEP, y: 0 },
      ArrowUp: { x: 0, y: -KEY_STEP },
      ArrowDown: { x: 0, y: KEY_STEP },
    }
    const step = delta[event.key]
    if (!step) return
    event.preventDefault()
    const position = { x: clamp(table.x + step.x), y: clamp(table.y + step.y) }
    setDragging({ id: table.id, position })
    move.mutate({ id: table.id, position })
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    add.mutate()
  }

  const error = add.error ?? update.error ?? remove.error ?? move.error

  return (
    <PageWrapper>
      <h1 className="text-2xl font-bold">Floor setup</h1>
      <p className="mt-1 mb-4 text-slate-600">Drag tables to match your dining room. Arrow keys also move a selected table.</p>
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <GlassCard className="p-3 sm:p-5">
          <div ref={mapRef} className="relative h-[26rem] touch-none rounded-xl bg-slate-100 sm:h-[34rem]">
            {tables.length === 0 && (
              <p className="absolute inset-0 flex items-center justify-center p-6 text-center text-slate-600">
                Add your first table using the form.
              </p>
            )}
            {tables.map((table) => {
              const position = dragging?.id === table.id ? dragging.position : table
              return (
                <motion.button
                  key={table.id}
                  type="button"
                  aria-label={`Move table ${table.label}`}
                  initial={false}
                  animate={{ left: `${position.x}%`, top: `${position.y}%` }}
                  transition={{ duration: 0 }}
                  onPointerDown={(event) => {
                    event.currentTarget.setPointerCapture(event.pointerId)
                    setDragging({ id: table.id, position: { x: table.x, y: table.y } })
                  }}
                  onPointerMove={(event) => onPointerMove(event, table.id)}
                  onPointerUp={() => onPointerUp(table.id)}
                  onKeyDown={(event) => onKeyDown(event, table)}
                  className="absolute flex h-[4.25rem] w-[4.25rem] -translate-x-1/2 -translate-y-1/2 cursor-grab flex-col items-center justify-center rounded-2xl bg-indigo-700 text-white shadow-md active:cursor-grabbing sm:h-24 sm:w-24"
                >
                  <span className="font-bold sm:text-lg">{table.label}</span>
                  <span className="text-xs">{table.seats} seats</span>
                </motion.button>
              )
            })}
          </div>
        </GlassCard>

        <div className="flex flex-col gap-4">
          <GlassCard>
            <h2 className="font-semibold">Add a table</h2>
            <form onSubmit={submit} className="mt-3 grid grid-cols-[1fr_5rem] gap-2">
              <AnimatedInput label="Name" placeholder="T1" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={20} required />
              <AnimatedInput label="Seats" type="number" min={1} max={50} value={seats} onChange={(e) => setSeats(e.target.value)} required />
              <GradientButton type="submit" className="col-span-2" disabled={add.isPending}>
                Add table
              </GradientButton>
            </form>
          </GlassCard>

          {error && <ErrorNote>{errorMessage(error)}</ErrorNote>}

          {tables.length > 0 && (
            <GlassCard>
              <h2 className="font-semibold">Your tables ({tables.length})</h2>
              <ul className="mt-3 flex max-h-96 flex-col gap-2 overflow-y-auto">
                {tables.map((table) => (
                  <li key={table.id} className="flex items-end gap-2">
                    <AnimatedInput
                      key={`label-${table.label}`}
                      className="min-w-0 flex-1"
                      label="Name"
                      defaultValue={table.label}
                      maxLength={20}
                      onBlur={(e) => {
                        const value = e.target.value.trim()
                        if (value && value !== table.label) update.mutate({ id: table.id, label: value })
                      }}
                    />
                    <AnimatedInput
                      key={`seats-${table.seats}`}
                      className="w-20"
                      label="Seats"
                      type="number"
                      min={1}
                      max={50}
                      defaultValue={table.seats}
                      onBlur={(e) => {
                        const value = Number(e.target.value)
                        if (value >= 1 && value <= 50 && value !== table.seats) update.mutate({ id: table.id, seats: value })
                      }}
                    />
                    <button
                      type="button"
                      aria-label={`Remove table ${table.label}`}
                      disabled={table.status !== 'free' || remove.isPending}
                      title={table.status !== 'free' ? 'Only a free table can be removed' : undefined}
                      onClick={() => remove.mutate(table.id)}
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <Trash2 size={18} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            </GlassCard>
          )}
        </div>
      </div>
    </PageWrapper>
  )
}
