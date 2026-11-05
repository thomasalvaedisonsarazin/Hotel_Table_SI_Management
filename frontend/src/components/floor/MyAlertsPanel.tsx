import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage } from '../../services/api'
import { staffService } from '../../services/staffService'
import type { StaffMember, StaffUpdate } from '../../types'
import { ErrorNote } from '../ui/Feedback'
import { GlassCard } from '../ui/GlassCard'
import { Toggle } from '../ui/Toggle'

export function MyAlertsPanel({ restaurantId, isDemo }: { restaurantId: number; isDemo: boolean }) {
  const queryClient = useQueryClient()
  const key = ['my-alerts', restaurantId]
  const mine = useQuery({ queryKey: key, queryFn: () => staffService.myAlerts(restaurantId) })
  const update = useMutation({
    mutationFn: (changes: Pick<StaffUpdate, 'on_shift' | 'notify_sms' | 'notify_whatsapp'>) =>
      staffService.updateMyAlerts(restaurantId, changes),
    onMutate: async (changes) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<StaffMember | null>(key)
      if (previous) queryClient.setQueryData(key, { ...previous, ...changes })
      return { previous }
    },
    onError: (_error, _changes, context) => queryClient.setQueryData(key, context?.previous),
    onSuccess: (member) => queryClient.setQueryData(key, member),
  })

  if (!mine.data) return null
  const me = mine.data

  return (
    <GlassCard>
      <h2 className="font-semibold">My alerts</h2>
      <Toggle label="I'm on shift" checked={me.on_shift} onChange={(value) => update.mutate({ on_shift: value })} />
      {me.phone ? (
        <>
          <Toggle label="Text message (SMS)" checked={me.notify_sms} onChange={(value) => update.mutate({ notify_sms: value })} />
          <Toggle label="WhatsApp" checked={me.notify_whatsapp} onChange={(value) => update.mutate({ notify_whatsapp: value })} />
          <p className="mt-1 text-xs text-slate-600">
            {isDemo
              ? 'This is a demo restaurant, so no real messages are sent.'
              : `Sent to ${me.phone} while you're on shift. Turning one on means you agree to receive work alerts.`}
          </p>
        </>
      ) : (
        <p className="mt-1 text-xs text-slate-600">Ask your manager to add your phone number to get alerts by message.</p>
      )}
      {update.isError && <ErrorNote>{errorMessage(update.error)}</ErrorNote>}
    </GlassCard>
  )
}
