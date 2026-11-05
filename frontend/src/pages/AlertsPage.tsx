import { useQuery } from '@tanstack/react-query'
import { BellRing, Sparkles } from 'lucide-react'
import { useRestaurant } from '../hooks/useRestaurant'
import { PageWrapper } from '../components/layout/PageWrapper'
import { ErrorNote, LoadingNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { formatDateTime, formatSeconds } from '../lib/format'
import { errorMessage } from '../services/api'
import { restaurantService } from '../services/restaurantService'
import type { Alert } from '../types'

const STATUS_LABEL: Record<Alert['status'], string> = {
  open: 'Open',
  acknowledged: "Someone's on it",
  resolved: 'Resolved',
}

function responseTime(alert: Alert): string {
  if (!alert.resolved_at) return '—'
  return formatSeconds((new Date(alert.resolved_at).getTime() - new Date(alert.created_at).getTime()) / 1000)
}

export function AlertsPage() {
  const { floor, restaurantId } = useRestaurant()
  const alerts = useQuery({
    queryKey: ['alerts', restaurantId, floor?.alerts.length],
    queryFn: () => restaurantService.alerts(restaurantId),
    refetchInterval: 15_000,
  })
  const timezone = floor?.restaurant.timezone ?? 'UTC'

  return (
    <PageWrapper className="max-w-4xl">
      <h1 className="mb-4 text-2xl font-bold">Alert history</h1>
      {alerts.isLoading && <LoadingNote />}
      {alerts.isError && <ErrorNote>{errorMessage(alerts.error)}</ErrorNote>}
      {alerts.data?.length === 0 && <p className="text-slate-600">No alerts yet.</p>}
      {alerts.data && alerts.data.length > 0 && (
        <GlassCard className="overflow-x-auto p-0">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-600">
              <tr>
                <th scope="col" className="p-3 font-medium">Time</th>
                <th scope="col" className="p-3 font-medium">Table</th>
                <th scope="col" className="p-3 font-medium">Alert</th>
                <th scope="col" className="p-3 font-medium">Status</th>
                <th scope="col" className="p-3 text-right font-medium">Time to resolve</th>
              </tr>
            </thead>
            <tbody>
              {alerts.data.map((alert) => (
                <tr key={alert.id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3 whitespace-nowrap">{formatDateTime(alert.created_at, timezone)}</td>
                  <td className="p-3 font-semibold">{alert.table_label}</td>
                  <td className="p-3">
                    <span className="flex items-center gap-2">
                      {alert.type === 'waiter' ? (
                        <BellRing size={16} className="text-red-700" aria-hidden="true" />
                      ) : (
                        <Sparkles size={16} className="text-amber-700" aria-hidden="true" />
                      )}
                      {alert.type === 'waiter' ? 'Needs a waiter' : 'Needs cleaning'}
                    </span>
                  </td>
                  <td className="p-3">{STATUS_LABEL[alert.status]}</td>
                  <td className="p-3 text-right tabular-nums">{responseTime(alert)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}
    </PageWrapper>
  )
}
