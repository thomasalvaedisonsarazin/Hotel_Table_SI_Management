import { useQuery } from '@tanstack/react-query'
import { PeakHeatmap } from '../components/analytics/PeakHeatmap'
import { PageWrapper } from '../components/layout/PageWrapper'
import { useRestaurant } from '../hooks/useRestaurant'
import { ErrorNote, LoadingNote, SampleDataBadge } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { cn, formatHour, formatSeconds, WEEKDAYS } from '../lib/format'
import { errorMessage } from '../services/api'
import { restaurantService } from '../services/restaurantService'
import { useState } from 'react'

const RANGES = [7, 28, 90]

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <GlassCard>
      <p className="text-sm text-slate-600">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-slate-600">{note}</p>}
    </GlassCard>
  )
}

export function AnalyticsPage() {
  const { restaurantId } = useRestaurant()
  const [days, setDays] = useState(7)
  const analytics = useQuery({
    queryKey: ['analytics', restaurantId, days],
    queryFn: () => restaurantService.analytics(restaurantId, days),
  })
  const data = analytics.data

  return (
    <PageWrapper>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex flex-wrap items-center gap-3 text-2xl font-bold">
          Analytics {data?.is_sample_data && <SampleDataBadge />}
        </h1>
        <div className="flex gap-1" role="group" aria-label="Date range">
          {RANGES.map((range) => (
            <button
              key={range}
              type="button"
              aria-pressed={days === range}
              onClick={() => setDays(range)}
              className={cn(
                'min-h-11 rounded-full px-4 text-sm font-medium',
                days === range ? 'bg-slate-900 text-white' : 'bg-white text-slate-800 hover:bg-slate-100',
              )}
            >
              {range} days
            </button>
          ))}
        </div>
      </div>

      {analytics.isLoading && <LoadingNote />}
      {analytics.isError && <ErrorNote>{errorMessage(analytics.error)}</ErrorNote>}

      {data?.parties === 0 && (
        <GlassCard>
          <p className="text-slate-600">
            No guests recorded in this period yet. Analytics fill in as tables are seated on the live floor.
          </p>
        </GlassCard>
      )}

      {data && data.parties > 0 && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Footfall (guests)" value={data.covers.toLocaleString()} note={`${data.parties.toLocaleString()} parties`} />
            <Stat
              label="Busiest time"
              value={data.peak_hour !== null && data.peak_weekday !== null ? `${WEEKDAYS[data.peak_weekday]} ${formatHour(data.peak_hour)}` : '—'}
            />
            <Stat label="Average table turn" value={data.avg_turn_minutes === null ? '—' : `${data.avg_turn_minutes} min`} />
            <Stat label="Average wait for waiter" value={formatSeconds(data.avg_wait_for_service_seconds)} />
            <Stat label="Average time to clean" value={formatSeconds(data.avg_cleaning_seconds)} />
            <Stat label="Waiter alerts" value={data.waiter_alerts.toLocaleString()} />
            <Stat label="Cleaning alerts" value={data.cleaning_alerts.toLocaleString()} />
            <Stat label="Guests per waiter" value={String(data.covers_per_waiter)} note="Used for staffing suggestions. Change it in Settings." />
          </div>
          <GlassCard>
            <h2 className="font-semibold">Peak hours and staffing</h2>
            <p className="mt-1 mb-3 text-sm text-slate-600">
              Average per day, by weekday and hour. Waiter numbers are a starting suggestion, not a rule.
            </p>
            <PeakHeatmap cells={data.heatmap} />
          </GlassCard>
        </div>
      )}
    </PageWrapper>
  )
}
