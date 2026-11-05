import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'
import { useRestaurant } from '../hooks/useRestaurant'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { GradientButton, SoftButton } from '../components/ui/Buttons'
import { ErrorNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { errorMessage } from '../services/api'
import { restaurantService } from '../services/restaurantService'
import type { Restaurant } from '../types'

function SettingsForm({ restaurant, onSaved }: { restaurant: Restaurant; onSaved: () => void }) {
  const [name, setName] = useState(restaurant.name)
  const [timezone, setTimezone] = useState(restaurant.timezone)
  const [waiterMinutes, setWaiterMinutes] = useState(String(restaurant.waiter_alert_seconds / 60))
  const [cleaningMinutes, setCleaningMinutes] = useState(String(restaurant.cleaning_alert_seconds / 60))
  const [turnMinutes, setTurnMinutes] = useState(String(restaurant.default_turn_minutes))
  const [coversPerWaiter, setCoversPerWaiter] = useState(String(restaurant.covers_per_waiter))
  const [seatConfirm, setSeatConfirm] = useState(String(restaurant.seat_confirm_seconds))
  const [vacateConfirm, setVacateConfirm] = useState(String(restaurant.vacate_confirm_seconds))
  const [serviceConfirm, setServiceConfirm] = useState(String(restaurant.service_confirm_seconds))
  const [cleanConfirm, setCleanConfirm] = useState(String(restaurant.clean_confirm_seconds))
  const [messageLimit, setMessageLimit] = useState(String(restaurant.daily_message_limit))
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      restaurantService.update(restaurant.id, {
        name: name.trim(),
        timezone: timezone.trim(),
        waiter_alert_seconds: Math.round(Number(waiterMinutes) * 60),
        cleaning_alert_seconds: Math.round(Number(cleaningMinutes) * 60),
        default_turn_minutes: Number(turnMinutes),
        covers_per_waiter: Number(coversPerWaiter),
        daily_message_limit: Number(messageLimit),
        seat_confirm_seconds: Number(seatConfirm),
        vacate_confirm_seconds: Number(vacateConfirm),
        service_confirm_seconds: Number(serviceConfirm),
        clean_confirm_seconds: Number(cleanConfirm),
      }),
    onSuccess: () => {
      setSaved(true)
      onSaved()
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setSaved(false)
    save.mutate()
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <GlassCard className="flex flex-col gap-3">
        <h2 className="font-semibold">Restaurant</h2>
        <AnimatedInput label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
        <AnimatedInput label="Timezone" hint="For example Asia/Kolkata. Used for peak hours." value={timezone} onChange={(e) => setTimezone(e.target.value)} required />
      </GlassCard>

      <GlassCard>
        <h2 className="font-semibold">Alerts and planning</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <AnimatedInput label="Waiter alert after (minutes)" type="number" min={0.25} max={60} step={0.25} value={waiterMinutes} onChange={(e) => setWaiterMinutes(e.target.value)} required />
          <AnimatedInput label="Cleaning alert after (minutes)" type="number" min={0} max={60} step={0.25} value={cleaningMinutes} onChange={(e) => setCleaningMinutes(e.target.value)} required />
          <AnimatedInput label="Typical table turn (minutes)" hint="Used until there is enough history." type="number" min={5} max={480} value={turnMinutes} onChange={(e) => setTurnMinutes(e.target.value)} required />
          <AnimatedInput label="Guests one waiter can handle" type="number" min={1} max={200} value={coversPerWaiter} onChange={(e) => setCoversPerWaiter(e.target.value)} required />
          <AnimatedInput label="Most messages per day" hint="A safety cap on SMS and WhatsApp costs." type="number" min={0} max={10000} value={messageLimit} onChange={(e) => setMessageLimit(e.target.value)} required />
        </div>
      </GlassCard>

      <GlassCard>
        <h2 className="font-semibold">Camera sensitivity</h2>
        <p className="mt-1 text-sm text-slate-600">How long something must be seen before it counts. Only used when a camera is connected.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <AnimatedInput label="Guests seated after (seconds)" type="number" min={0} max={600} value={seatConfirm} onChange={(e) => setSeatConfirm(e.target.value)} required />
          <AnimatedInput label="Guests gone after (seconds)" type="number" min={0} max={1800} value={vacateConfirm} onChange={(e) => setVacateConfirm(e.target.value)} required />
          <AnimatedInput label="Waiter visit after (seconds)" type="number" min={0} max={300} value={serviceConfirm} onChange={(e) => setServiceConfirm(e.target.value)} required />
          <AnimatedInput label="Table cleaned after (seconds)" type="number" min={0} max={600} value={cleanConfirm} onChange={(e) => setCleanConfirm(e.target.value)} required />
        </div>
      </GlassCard>

      {save.isError && <ErrorNote>{errorMessage(save.error)}</ErrorNote>}
      <div className="flex items-center gap-3">
        <GradientButton type="submit" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save changes'}
        </GradientButton>
        {saved && <p role="status" className="text-sm font-medium text-green-800">Saved</p>}
      </div>
    </form>
  )
}

export function SettingsPage() {
  const { floor, refresh, restaurantId } = useRestaurant()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const rotate = useMutation({
    mutationFn: () => restaurantService.rotateKey(restaurantId),
    onSuccess: (key) => {
      setApiKey(key)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => restaurantService.remove(restaurantId),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['floor', restaurantId] })
      void queryClient.invalidateQueries({ queryKey: ['restaurants'] })
      navigate('/dashboard')
    },
  })

  if (!floor) return null
  const hasKey = floor.restaurant.has_api_key
  const isOwner = floor.restaurant.my_role === 'owner'

  return (
    <PageWrapper className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-2xl font-bold">Settings</h1>
      <SettingsForm restaurant={floor.restaurant} onSaved={refresh} />

      {isOwner && <GlassCard>
        <h2 className="font-semibold">Camera connection key</h2>
        <p className="mt-1 text-sm text-slate-600">
          A camera worker uses this key to send table observations to <code className="break-all">/api/v1/ingest/observations</code>.
          {hasKey ? ' Creating a new key stops the old one working.' : ''}
        </p>
        {apiKey && (
          <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm">
            <p className="font-semibold text-amber-950">Copy this now. It won't be shown again.</p>
            <code className="mt-1 block break-all">{apiKey}</code>
          </div>
        )}
        <SoftButton className="mt-3" disabled={rotate.isPending} onClick={() => rotate.mutate()}>
          {hasKey ? 'Create a new key' : 'Create key'}
        </SoftButton>
        {rotate.isError && <ErrorNote>{errorMessage(rotate.error)}</ErrorNote>}
      </GlassCard>}

      {isOwner && <GlassCard>
        <h2 className="font-semibold">Delete restaurant</h2>
        <p className="mt-1 text-sm text-slate-600">Permanently removes its tables, history and alerts. This can't be undone.</p>
        {confirmDelete ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
              className="min-h-11 rounded-full bg-red-700 px-5 text-sm font-semibold text-white disabled:opacity-50"
            >
              Yes, delete {floor.restaurant.name}
            </button>
            <SoftButton onClick={() => setConfirmDelete(false)}>Keep it</SoftButton>
          </div>
        ) : (
          <SoftButton className="mt-3 text-red-800" onClick={() => setConfirmDelete(true)}>
            Delete restaurant
          </SoftButton>
        )}
        {remove.isError && <ErrorNote>{errorMessage(remove.error)}</ErrorNote>}
      </GlassCard>}
    </PageWrapper>
  )
}
