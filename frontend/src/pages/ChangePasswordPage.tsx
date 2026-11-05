import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { MeshBackground } from '../components/layout/MeshBackground'
import { PageWrapper } from '../components/layout/PageWrapper'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { GradientButton } from '../components/ui/Buttons'
import { ErrorNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../services/api'

export function ChangePasswordPage() {
  const { user, changePassword } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const required = user?.must_change_password ?? false

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (next !== confirm) {
      setError("The new passwords don't match.")
      return
    }
    setBusy(true)
    setError('')
    try {
      await changePassword(current, next)
      navigate('/dashboard', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <PageWrapper className="flex min-h-screen items-center justify-center">
      <MeshBackground />
      <div className="w-full max-w-md">
        <GlassCard className="p-6">
          <h1 className="text-2xl font-bold">{required ? 'Choose your password' : 'Change your password'}</h1>
          <p className="mt-1 mb-5 text-sm text-slate-600">
            {required ? 'You logged in with a temporary password. Choose your own to continue.' : 'This logs you out on your other devices.'}
          </p>
          <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
            <AnimatedInput label={required ? 'Temporary password' : 'Current password'} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            <AnimatedInput label="New password" type="password" autoComplete="new-password" hint="At least 8 characters." minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
            <AnimatedInput label="Repeat new password" type="password" autoComplete="new-password" minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            <ErrorNote>{error}</ErrorNote>
            <GradientButton type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save password'}
            </GradientButton>
          </form>
        </GlassCard>
      </div>
    </PageWrapper>
  )
}
