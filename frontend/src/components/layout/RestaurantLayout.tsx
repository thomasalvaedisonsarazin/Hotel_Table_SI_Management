import { useMutation } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { BellRing, X } from 'lucide-react'
import { NavLink, Outlet, useParams } from 'react-router-dom'
import { useLiveFloor } from '../../hooks/useLiveFloor'
import type { RestaurantContext } from '../../hooks/useRestaurant'
import { cn } from '../../lib/format'
import { restaurantService } from '../../services/restaurantService'
import { ErrorNote, LoadingNote } from '../ui/Feedback'
import { SoftButton } from '../ui/Buttons'
import { PageWrapper } from './PageWrapper'
import { TopBar } from './TopBar'

const LINKS = [
  { to: 'floor', label: 'Live floor', managerOnly: false },
  { to: 'alerts', label: 'Alerts', managerOnly: false },
  { to: 'analytics', label: 'Analytics', managerOnly: true },
  { to: 'setup', label: 'Floor setup', managerOnly: true },
  { to: 'staff', label: 'Staff', managerOnly: true },
  { to: 'settings', label: 'Settings', managerOnly: true },
]

export function RestaurantLayout() {
  const { id } = useParams()
  const restaurantId = Number(id)
  const live = useLiveFloor(restaurantId)
  const { floor } = live

  const simulator = useMutation({
    mutationFn: (enabled: boolean) => restaurantService.setSimulator(restaurantId, enabled),
    onSuccess: live.refresh,
  })

  const alertTable = floor?.tables.find((table) => table.id === live.newAlert?.tableId)
  const isStaff = floor?.restaurant.my_role === 'staff'
  const openAlerts = floor?.alerts.filter((alert) => alert.status === 'open').length ?? 0

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar />
      {floor?.restaurant.is_demo && (
        <div className="bg-amber-100 text-amber-950">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm sm:px-6">
            <p>
              <strong>Simulated demo.</strong> No cameras are connected. Activity, alerts and analytics here are
              generated, and timings are sped up.
            </p>
            {!isStaff && <SoftButton
              className="min-h-9 py-1"
              disabled={simulator.isPending}
              onClick={() => simulator.mutate(!floor.restaurant.simulator_enabled)}
            >
              {floor.restaurant.simulator_enabled ? 'Pause simulation' : 'Resume simulation'}
            </SoftButton>}
          </div>
        </div>
      )}
      <nav aria-label="Restaurant" className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2 sm:px-4">
          {LINKS.filter((link) => !(link.managerOnly && isStaff)).map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cn(
                  'flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm font-medium whitespace-nowrap',
                  isActive
                    ? 'border-indigo-700 text-indigo-800'
                    : 'border-transparent text-slate-600 hover:text-slate-900',
                )
              }
            >
              {link.label}
              {link.to === 'alerts' && openAlerts > 0 && (
                <span className="rounded-full bg-red-700 px-2 py-0.5 text-xs font-bold text-white">
                  {openAlerts}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {live.isLoading && <LoadingNote />}
      {live.isError && !floor && (
        <PageWrapper>
          <ErrorNote>This restaurant could not be loaded. It may have been removed.</ErrorNote>
        </PageWrapper>
      )}
      {floor && <Outlet context={{ ...live, restaurantId } satisfies RestaurantContext} />}

      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-40 flex justify-end">
        <AnimatePresence>
          {live.newAlert && (
            <motion.div
              role="alert"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              className="pointer-events-auto flex w-full max-w-sm items-center gap-3 rounded-2xl bg-slate-900 p-4 text-white shadow-xl"
            >
              <BellRing className="shrink-0" size={22} aria-hidden="true" />
              <p className="flex-1 text-sm font-medium">
                Table {alertTable?.label ?? ''}:{' '}
                {live.newAlert.type === 'waiter' ? 'guests are waiting for a waiter' : 'needs cleaning'}
              </p>
              <button
                type="button"
                aria-label="Dismiss alert"
                onClick={live.dismissAlert}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full hover:bg-white/10"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
