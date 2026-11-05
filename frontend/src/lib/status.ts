import type { TableStatus } from '../types'

export const STATUS_STYLE: Record<TableStatus, { label: string; tile: string; dot: string }> = {
  free: { label: 'Free', tile: 'bg-green-700 text-white', dot: 'bg-green-700' },
  occupied: { label: 'Occupied', tile: 'bg-red-700 text-white', dot: 'bg-red-700' },
  needs_cleaning: { label: 'Needs cleaning', tile: 'bg-amber-400 text-slate-950', dot: 'bg-amber-400' },
}
