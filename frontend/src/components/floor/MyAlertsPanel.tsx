import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { setAlarmEnabled, useAlarmState } from '../../lib/tabletAlarm'
import { errorMessage } from '../../services/api'
import { isPhoneApp, phone, registerThisPhone } from '../../services/phoneApp'
import { staffService } from '../../services/staffService'
import type { StaffMember, StaffUpdate } from '../../types'
import { SoftButton } from '../ui/Buttons'
import { ErrorNote } from '../ui/Feedback'
import { GlassCard } from '../ui/GlassCard'
import { Toggle } from '../ui/Toggle'

type AlertChanges = Pick<StaffUpdate, 'on_shift' | 'notify_sms' | 'notify_whatsapp' | 'notify_push'>

function ThisDeviceAlarm() {
  const alarm = useAlarmState()
  return (
    <>
      <Toggle label="Sound an alarm on this device" checked={alarm.enabled} onChange={setAlarmEnabled} />
      <p className="mt-1 text-xs text-slate-600">
        Good for a tablet at the host stand. It rings while an alert is waiting, but only with this page open and the
        screen on.
      </p>
    </>
  )
}

function PhoneRing({ me, onChange }: { me: StaffMember | null; onChange: (changes: AlertChanges) => void }) {
  const status = useQuery({ queryKey: ['phone-status'], queryFn: registerThisPhone })
  const test = useMutation({ mutationFn: () => phone.testRing() })
  const data = status.data

  return (
    <>
      {me ? (
        <Toggle label="Ring this phone" checked={me.notify_push} onChange={(value) => onChange({ notify_push: value })} />
      ) : (
        <p className="mt-1 text-xs text-slate-600">Add yourself on the Staff page to get alerts on this phone.</p>
      )}
      {status.isError && <ErrorNote>This phone couldn't be set up for alerts. {errorMessage(status.error)}</ErrorNote>}
      {data && !data.firebaseReady && (
        <p className="mt-1 rounded-xl bg-amber-100 p-2 text-xs text-amber-950">
          This version of the app can only ring for a test. Alerts need the version connected to Firebase.
        </p>
      )}
      {data && (!data.notificationsAllowed || !data.ringEnabled) && (
        <div className="mt-1 rounded-xl bg-red-50 p-2 text-xs text-red-900">
          <p className="font-semibold">This phone won't ring. Notifications or their sound are turned off.</p>
          <SoftButton className="mt-2" onClick={() => void phone.openNotificationSettings()}>
            Open notification settings
          </SoftButton>
        </div>
      )}
      {data && !data.batteryUnrestricted && (
        <div className="mt-1 rounded-xl bg-amber-100 p-2 text-xs text-amber-950">
          <p>Battery saving can delay alerts. On this app's settings page, set battery use to Unrestricted.</p>
          <SoftButton className="mt-2" onClick={() => void phone.openAppSettings()}>
            Open app settings
          </SoftButton>
        </div>
      )}
      <SoftButton className="mt-2" disabled={test.isPending} onClick={() => test.mutate()}>
        Test the ring
      </SoftButton>
    </>
  )
}

export function MyAlertsPanel({ restaurantId, isDemo }: { restaurantId: number; isDemo: boolean }) {
  const queryClient = useQueryClient()
  const key = ['my-alerts', restaurantId]
  const mine = useQuery({ queryKey: key, queryFn: () => staffService.myAlerts(restaurantId) })
  const update = useMutation({
    mutationFn: (changes: AlertChanges) => staffService.updateMyAlerts(restaurantId, changes),
    onMutate: async (changes) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<StaffMember | null>(key)
      if (previous) queryClient.setQueryData(key, { ...previous, ...changes })
      return { previous }
    },
    onError: (_error, _changes, context) => queryClient.setQueryData(key, context?.previous),
    onSuccess: (member) => queryClient.setQueryData(key, member),
  })

  if (mine.isLoading) return null
  const me = mine.data ?? null

  return (
    <GlassCard>
      <h2 className="font-semibold">My alerts</h2>
      {me && <Toggle label="I'm on shift" checked={me.on_shift} onChange={(value) => update.mutate({ on_shift: value })} />}
      {isPhoneApp() ? <PhoneRing me={me} onChange={update.mutate} /> : <ThisDeviceAlarm />}
      {me &&
        (me.phone ? (
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
        ))}
      {update.isError && <ErrorNote>{errorMessage(update.error)}</ErrorNote>}
    </GlassCard>
  )
}
