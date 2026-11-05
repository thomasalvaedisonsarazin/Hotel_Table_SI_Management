import { useMutation } from '@tanstack/react-query'
import { BellRing, Sparkles } from 'lucide-react'
import { formatTimer } from '../../lib/format'
import { restaurantService } from '../../services/restaurantService'
import type { Alert } from '../../types'
import { SoftButton } from '../ui/Buttons'
import { GlassCard } from '../ui/GlassCard'

interface AlertsPanelProps {
  restaurantId: number
  alerts: Alert[]
  now: number
  onChanged: () => void
}

export function AlertsPanel({ restaurantId, alerts, now, onChanged }: AlertsPanelProps) {
  const acknowledge = useMutation({
    mutationFn: (alertId: number) => restaurantService.acknowledgeAlert(restaurantId, alertId),
    onSuccess: onChanged,
  })

  return (
    <GlassCard>
      <h2 className="font-semibold">Needs attention</h2>
      {alerts.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">Nothing right now.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {alerts.map((alert) => (
            <li key={alert.id} className="flex items-center gap-3 rounded-xl bg-slate-100 p-2.5">
              {alert.type === 'waiter' ? (
                <BellRing className="shrink-0 text-red-700" size={20} aria-hidden="true" />
              ) : (
                <Sparkles className="shrink-0 text-amber-700" size={20} aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-semibold">
                  Table {alert.table_label}: {alert.type === 'waiter' ? 'needs a waiter' : 'needs cleaning'}
                </p>
                <p className="text-slate-600">
                  <span className="font-mono tabular-nums">{formatTimer(alert.created_at, now)}</span> since alert
                </p>
              </div>
              {alert.status === 'open' ? (
                <SoftButton className="px-3" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate(alert.id)}>
                  On it
                </SoftButton>
              ) : (
                <span className="px-1 text-xs font-medium text-slate-600">Someone's on it</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </GlassCard>
  )
}
