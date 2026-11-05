import { motion } from 'framer-motion'
import { BellRing, Check, Sparkles, Users } from 'lucide-react'
import { cn, formatTimer } from '../../lib/format'
import { STATUS_STYLE } from '../../lib/status'
import type { Alert, FloorTable, TableStatus } from '../../types'

const STATUS_SHORT: Record<TableStatus, string> = {
  free: 'Free',
  occupied: 'Occupied',
  needs_cleaning: 'To clean',
}

interface TableTileProps {
  table: FloorTable
  alert?: Alert
  now: number
  onSelect: () => void
}

export function TableTile({ table, alert, now, onSelect }: TableTileProps) {
  const style = STATUS_STYLE[table.status]
  const timerFrom = table.status === 'occupied' ? table.seated_at : table.vacated_at
  const alertLabel = alert ? (alert.type === 'waiter' ? 'waiting for a waiter' : 'cleaning overdue') : null

  return (
    <motion.button
      type="button"
      onClick={onSelect}
      aria-label={[
        `Table ${table.label}`,
        style.label,
        table.party_size ? `${table.party_size} guests` : `${table.seats} seats`,
        alertLabel,
      ]
        .filter(Boolean)
        .join(', ')}
      initial={false}
      animate={{ left: `${table.x}%`, top: `${table.y}%` }}
      transition={{ duration: 0 }}
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.97 }}
      className={cn(
        'absolute flex h-[4.25rem] w-[4.25rem] -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-2xl p-1 shadow-md transition-colors duration-300 sm:h-28 sm:w-28',
        style.tile,
        alert && 'ring-2 ring-slate-950 ring-offset-1 sm:ring-4 sm:ring-offset-2',
      )}
    >
      {alert && (
        <span className="absolute -top-2 -right-2 flex h-7 w-7 animate-pulse items-center justify-center rounded-full bg-slate-950 text-white">
          <BellRing size={15} aria-hidden="true" />
        </span>
      )}
      <span className="text-base leading-tight font-bold sm:text-xl">{table.label}</span>
      <span className="hidden text-xs font-medium sm:block">{style.label}</span>
      <span className="text-[0.7rem] font-medium sm:hidden">{STATUS_SHORT[table.status]}</span>
      {timerFrom ? (
        <span className="font-mono text-xs font-semibold tabular-nums sm:text-sm">{formatTimer(timerFrom, now)}</span>
      ) : (
        <span className="flex items-center gap-1 text-xs">
          <Users size={12} aria-hidden="true" />
          {table.seats}
        </span>
      )}
      {table.status === 'occupied' && table.first_served_at && (
        <Check className="absolute top-1 left-1 hidden sm:block" size={14} aria-label="Waiter has visited" />
      )}
      {table.status === 'needs_cleaning' && (
        <Sparkles className="absolute top-1 left-1 hidden sm:block" size={14} aria-hidden="true" />
      )}
    </motion.button>
  )
}
