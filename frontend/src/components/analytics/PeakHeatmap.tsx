import { useState } from 'react'
import { businessHours, cn, formatHour, WEEKDAYS } from '../../lib/format'
import type { HeatmapCell } from '../../types'
import { SoftButton } from '../ui/Buttons'

// One hue from light to dark, because this shows a single quantity from low to high.
const RAMP = [
  'bg-[#cde2fb] text-slate-900',
  'bg-[#9ec5f4] text-slate-900',
  'bg-[#6da7ec] text-slate-900',
  'bg-[#3987e5] text-slate-950',
  'bg-[#256abf] text-white',
  'bg-[#184f95] text-white',
  'bg-[#0d366b] text-white',
]

type Metric = 'covers' | 'waiters'

export function PeakHeatmap({ cells }: { cells: HeatmapCell[] }) {
  const [metric, setMetric] = useState<Metric>('covers')
  const [active, setActive] = useState<HeatmapCell | null>(null)
  const [showTable, setShowTable] = useState(false)

  const hourRange = businessHours(cells.map((cell) => cell.hour))
  const lookup = new Map(cells.map((cell) => [`${cell.weekday}-${cell.hour}`, cell]))
  const valueOf = (cell: HeatmapCell) => (metric === 'covers' ? cell.avg_covers : cell.suggested_waiters)
  const max = Math.max(...cells.map(valueOf), 1)
  const rampClass = (value: number) => RAMP[Math.min(RAMP.length - 1, Math.floor((value / max) * RAMP.length))]
  const describe = (cell: HeatmapCell) =>
    `${WEEKDAYS[cell.weekday]} ${formatHour(cell.hour)}: ${cell.avg_covers} guests on average, ${cell.suggested_waiters} ${cell.suggested_waiters === 1 ? 'waiter' : 'waiters'} suggested`

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Value shown">
        {(['covers', 'waiters'] as const).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={metric === option}
            onClick={() => setMetric(option)}
            className={cn(
              'min-h-11 rounded-full px-4 text-sm font-medium',
              metric === option ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-800 hover:bg-slate-200',
            )}
          >
            {option === 'covers' ? 'Guests present' : 'Suggested waiters'}
          </button>
        ))}
      </div>

      <p className="mb-2 min-h-5 text-sm text-slate-700" aria-live="polite">
        {active ? describe(active) : 'Hover over or tap a cell for details.'}
      </p>

      <div className="overflow-x-auto pb-2">
        <div className="min-w-[36rem]">
          <div className="flex gap-0.5 pl-11">
            {hourRange.map((hour) => (
              <div key={hour} className="flex-1 text-center text-xs text-slate-600">
                {String(hour).padStart(2, '0')}
              </div>
            ))}
          </div>
          {WEEKDAYS.map((name, weekday) => (
            <div key={name} className="mt-0.5 flex items-center gap-0.5">
              <div className="w-10 text-xs text-slate-600">{name}</div>
              {hourRange.map((hour) => {
                const cell = lookup.get(`${weekday}-${hour}`)
                if (!cell) return <div key={hour} className="h-9 flex-1 rounded bg-slate-100" />
                return (
                  <button
                    key={hour}
                    type="button"
                    aria-label={describe(cell)}
                    title={describe(cell)}
                    onMouseEnter={() => setActive(cell)}
                    onFocus={() => setActive(cell)}
                    className={cn('h-9 flex-1 rounded text-xs font-medium tabular-nums', rampClass(valueOf(cell)))}
                  >
                    {metric === 'covers' ? Math.round(cell.avg_covers) : cell.suggested_waiters}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <SoftButton className="mt-2" aria-expanded={showTable} onClick={() => setShowTable((shown) => !shown)}>
        {showTable ? 'Hide table' : 'View as table'}
      </SoftButton>
      {showTable && (
        <div className="mt-3 max-h-80 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-slate-600">
              <tr>
                <th scope="col" className="p-2 font-medium">Day</th>
                <th scope="col" className="p-2 font-medium">Hour</th>
                <th scope="col" className="p-2 text-right font-medium">Avg guests</th>
                <th scope="col" className="p-2 text-right font-medium">Suggested waiters</th>
              </tr>
            </thead>
            <tbody>
              {cells.map((cell) => (
                <tr key={`${cell.weekday}-${cell.hour}`} className="border-t border-slate-100">
                  <td className="p-2">{WEEKDAYS[cell.weekday]}</td>
                  <td className="p-2">{formatHour(cell.hour)}</td>
                  <td className="p-2 text-right tabular-nums">{cell.avg_covers}</td>
                  <td className="p-2 text-right tabular-nums">{cell.suggested_waiters}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
