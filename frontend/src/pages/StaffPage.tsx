import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { PageWrapper } from '../components/layout/PageWrapper'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { GradientButton, SoftButton } from '../components/ui/Buttons'
import { ErrorNote, LoadingNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { Toggle } from '../components/ui/Toggle'
import { useRestaurant } from '../hooks/useRestaurant'
import { formatDateTime } from '../lib/format'
import { errorMessage } from '../services/api'
import { staffService } from '../services/staffService'
import type { NotificationStatus, StaffInput, StaffMember, StaffRole, StaffUpdate, TestSendResult } from '../types'

const PHONE_HINT = 'With country code, like +919876543210'
const CONSENT_LABEL = 'This person agreed to receive work alerts on this number'

const DELIVERY_LABEL: Record<string, string> = {
  pending: 'Waiting to send',
  sent: 'Sent',
  logged: 'Not sent (recorded only)',
  failed: 'Failed',
  skipped: 'Not needed',
}

function SendingNotice({ status }: { status: NotificationStatus }) {
  if (status.is_demo) {
    return (
      <p className="rounded-2xl bg-amber-100 p-4 text-sm text-amber-950">
        <strong>Demo restaurants never send real messages.</strong> Add a real restaurant to use SMS and WhatsApp alerts.
      </p>
    )
  }
  if (status.provider === 'log') {
    return (
      <p className="rounded-2xl bg-amber-100 p-4 text-sm text-amber-950">
        <strong>Messages aren't being sent yet.</strong> Alerts still appear in the app, and text messages are only
        recorded until a Twilio account is connected. The README explains how.
      </p>
    )
  }
  return (
    <p className="rounded-2xl bg-green-50 p-4 text-sm text-green-950">
      <strong>Message sending is on.</strong> SMS {status.can_send_sms ? 'ready' : 'not set up'}, WhatsApp{' '}
      {status.can_send_whatsapp ? 'ready' : 'not set up'}. {status.sent_last_24h} of {status.daily_limit} daily messages used.
    </p>
  )
}

function OneTimePassword({ email, password, onDone }: { email: string; password: string; onDone: () => void }) {
  return (
    <div role="status" className="rounded-2xl border-2 border-amber-400 bg-amber-50 p-4 text-sm">
      <p className="font-semibold text-amber-950">Give these login details to the staff member. The password won't be shown again.</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-slate-700">Email</dt>
        <dd className="font-medium break-all">{email}</dd>
        <dt className="text-slate-700">Temporary password</dt>
        <dd className="font-mono font-semibold break-all">{password}</dd>
      </dl>
      <p className="mt-2 text-slate-700">They'll be asked to choose their own password when they first log in.</p>
      <SoftButton className="mt-3" onClick={onDone}>
        I've copied this
      </SoftButton>
    </div>
  )
}

function AddStaffForm({ restaurantId, isOwner, onCreated }: { restaurantId: number; isOwner: boolean; onCreated: (member: StaffMember) => void }) {
  const empty: StaffInput = {
    full_name: '',
    email: '',
    role: 'staff',
    phone: '',
    alerts_consented: false,
    notify_sms: false,
    notify_whatsapp: false,
  }
  const [form, setForm] = useState<StaffInput>(empty)
  const set = (changes: Partial<StaffInput>) => setForm((current) => ({ ...current, ...changes }))
  const add = useMutation({
    mutationFn: () => staffService.add(restaurantId, { ...form, full_name: form.full_name.trim() }),
    onSuccess: (member) => {
      setForm(empty)
      onCreated(member)
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    add.mutate()
  }
  const hasPhone = form.phone.trim() !== ''

  return (
    <GlassCard>
      <h2 className="font-semibold">Add a staff member</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <AnimatedInput label="Full name" value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} maxLength={100} required />
        <AnimatedInput
          label="Email (used to log in)"
          type="email"
          value={form.email}
          hint={isOwner ? 'Enter your own email to get alerts on your phone yourself.' : undefined}
          onChange={(e) => set({ email: e.target.value })}
          required
        />
        <AnimatedInput label="Phone (optional)" type="tel" hint={PHONE_HINT} value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
        {isOwner && (
          <div>
            <label htmlFor="staff-role" className="mb-1 block text-sm font-medium text-slate-700">
              Role
            </label>
            <select
              id="staff-role"
              value={form.role}
              onChange={(e) => set({ role: e.target.value as StaffRole })}
              className="min-h-11 w-full rounded-xl border-2 border-slate-200 bg-white px-3 py-2 outline-none focus:border-indigo-600"
            >
              <option value="staff">Staff: live floor and alerts</option>
              <option value="manager">Manager: also staff, setup and analytics</option>
            </select>
          </div>
        )}
        {hasPhone && (
          <div className="sm:col-span-2">
            <Toggle label={CONSENT_LABEL} checked={form.alerts_consented} onChange={(value) => set({ alerts_consented: value, ...(value ? {} : { notify_sms: false, notify_whatsapp: false }) })} />
            <div className="flex flex-wrap gap-x-6">
              <Toggle label="Text message (SMS)" checked={form.notify_sms} disabled={!form.alerts_consented} onChange={(value) => set({ notify_sms: value })} />
              <Toggle label="WhatsApp" checked={form.notify_whatsapp} disabled={!form.alerts_consented} onChange={(value) => set({ notify_whatsapp: value })} />
            </div>
          </div>
        )}
        <div className="sm:col-span-2">
          <GradientButton type="submit" disabled={add.isPending}>
            {add.isPending ? 'Adding…' : 'Add staff member'}
          </GradientButton>
        </div>
        {add.isError && (
          <div className="sm:col-span-2">
            <ErrorNote>{errorMessage(add.error)}</ErrorNote>
          </div>
        )}
      </form>
    </GlassCard>
  )
}

interface MemberCardProps {
  restaurantId: number
  member: StaffMember
  canManage: boolean
  onChanged: () => void
  onPassword: (email: string, password: string) => void
}

function MemberCard({ restaurantId, member, canManage, onChanged, onPassword }: MemberCardProps) {
  const [results, setResults] = useState<TestSendResult[] | null>(null)
  const update = useMutation({
    mutationFn: (changes: StaffUpdate) => staffService.update(restaurantId, member.id, changes),
    onSuccess: onChanged,
  })
  const reset = useMutation({
    mutationFn: () => staffService.resetPassword(restaurantId, member.id),
    onSuccess: (password) => onPassword(member.email, password),
  })
  const test = useMutation({
    mutationFn: () => staffService.sendTest(restaurantId, member.id),
    onSuccess: setResults,
  })
  const error = update.error ?? reset.error ?? test.error
  const canMessage = Boolean(member.phone) && member.alerts_consented

  return (
    <GlassCard>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold break-words">
            {member.full_name || member.email}
            {!member.is_active && <span className="ml-2 text-sm font-medium text-red-800">Deactivated</span>}
          </p>
          <p className="text-sm break-all text-slate-600">{member.email}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-800">
          {member.is_owner ? 'Owner' : member.role === 'manager' ? 'Manager' : 'Staff'}
        </span>
      </div>

      {canManage ? (
        <div className="mt-3">
          <AnimatedInput
            key={member.phone ?? 'no-phone'}
            label="Phone"
            type="tel"
            hint={PHONE_HINT}
            defaultValue={member.phone ?? ''}
            onBlur={(e) => {
              const value = e.target.value.trim()
              if (value !== (member.phone ?? '')) update.mutate({ phone: value })
            }}
          />
          {member.phone && (
            <Toggle label={CONSENT_LABEL} checked={member.alerts_consented} disabled={update.isPending} onChange={(value) => update.mutate({ alerts_consented: value })} />
          )}
          <div className="grid gap-x-4 sm:grid-cols-2">
            <Toggle label="Text message (SMS)" checked={member.notify_sms} disabled={!canMessage || update.isPending} onChange={(value) => update.mutate({ notify_sms: value })} />
            <Toggle label="WhatsApp" checked={member.notify_whatsapp} disabled={!canMessage || update.isPending} onChange={(value) => update.mutate({ notify_whatsapp: value })} />
            <Toggle label="Waiter alerts" checked={member.notify_waiter_alerts} disabled={update.isPending} onChange={(value) => update.mutate({ notify_waiter_alerts: value })} />
            <Toggle label="Cleaning alerts" checked={member.notify_cleaning_alerts} disabled={update.isPending} onChange={(value) => update.mutate({ notify_cleaning_alerts: value })} />
            <Toggle label="On shift" checked={member.on_shift} disabled={update.isPending} onChange={(value) => update.mutate({ on_shift: value })} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <SoftButton disabled={!(member.notify_sms || member.notify_whatsapp) || test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? 'Sending…' : 'Send a test alert'}
            </SoftButton>
            {!member.is_owner && (
              <>
                <SoftButton disabled={reset.isPending} onClick={() => reset.mutate()}>
                  Reset password
                </SoftButton>
                <SoftButton
                  className={member.is_active ? 'text-red-800' : undefined}
                  disabled={update.isPending}
                  onClick={() => update.mutate({ is_active: !member.is_active })}
                >
                  {member.is_active ? 'Deactivate' : 'Reactivate'}
                </SoftButton>
              </>
            )}
          </div>
          {results && (
            <ul className="mt-2 text-sm" role="status">
              {results.map((result) => (
                <li key={result.channel}>
                  <span className="font-medium">{result.channel === 'sms' ? 'SMS' : 'WhatsApp'}:</span>{' '}
                  {result.status === 'sent'
                    ? 'sent. Check the phone to confirm it arrived.'
                    : result.status === 'logged'
                      ? 'not sent, because no message provider is connected yet.'
                      : `failed. ${result.error ?? ''}`}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-600">Only the owner can change a manager.</p>
      )}
      {error && (
        <div className="mt-2">
          <ErrorNote>{errorMessage(error)}</ErrorNote>
        </div>
      )}
    </GlassCard>
  )
}

export function StaffPage() {
  const { floor, restaurantId } = useRestaurant()
  const queryClient = useQueryClient()
  const [password, setPassword] = useState<{ email: string; password: string } | null>(null)
  const staff = useQuery({ queryKey: ['staff', restaurantId], queryFn: () => staffService.list(restaurantId) })
  const status = useQuery({
    queryKey: ['notifications', restaurantId],
    queryFn: () => staffService.notifications(restaurantId),
    refetchInterval: (query) =>
      query.state.data?.recent.some((delivery) => delivery.status === 'pending') ? 3_000 : 15_000,
  })
  const isOwner = floor?.restaurant.my_role === 'owner'
  const timezone = floor?.restaurant.timezone ?? 'UTC'

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['staff', restaurantId] })
    void queryClient.invalidateQueries({ queryKey: ['my-alerts', restaurantId] })
  }

  return (
    <PageWrapper className="flex max-w-4xl flex-col gap-4">
      <h1 className="text-2xl font-bold">Staff and alerts</h1>
      {status.data && <SendingNotice status={status.data} />}
      {password && <OneTimePassword email={password.email} password={password.password} onDone={() => setPassword(null)} />}
      <AddStaffForm
        restaurantId={restaurantId}
        isOwner={isOwner}
        onCreated={(member) => {
          refresh()
          if (member.temporary_password) setPassword({ email: member.email, password: member.temporary_password })
        }}
      />

      {staff.isLoading && <LoadingNote />}
      {staff.isError && <ErrorNote>{errorMessage(staff.error)}</ErrorNote>}
      {staff.data?.length === 0 && <p className="text-slate-600">No staff added yet.</p>}
      {staff.data?.map((member) => (
        <MemberCard
          key={member.id}
          restaurantId={restaurantId}
          member={member}
          canManage={isOwner || member.role !== 'manager'}
          onChanged={refresh}
          onPassword={(email, value) => setPassword({ email, password: value })}
        />
      ))}

      {status.data && status.data.recent.length > 0 && (
        <GlassCard className="overflow-x-auto p-0">
          <h2 className="p-4 pb-2 font-semibold">Recent messages</h2>
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-600">
              <tr>
                <th scope="col" className="p-3 font-medium">Time</th>
                <th scope="col" className="p-3 font-medium">To</th>
                <th scope="col" className="p-3 font-medium">Table</th>
                <th scope="col" className="p-3 font-medium">Channel</th>
                <th scope="col" className="p-3 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {status.data.recent.map((delivery) => (
                <tr key={delivery.id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3 whitespace-nowrap">{formatDateTime(delivery.created_at, timezone)}</td>
                  <td className="p-3">{delivery.member_name}</td>
                  <td className="p-3 font-semibold">{delivery.table_label}</td>
                  <td className="p-3">{delivery.channel === 'sms' ? 'SMS' : 'WhatsApp'}</td>
                  <td className="p-3">
                    {DELIVERY_LABEL[delivery.status] ?? delivery.status}
                    {delivery.error && <span className="block text-xs text-slate-600">{delivery.error}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}
    </PageWrapper>
  )
}
