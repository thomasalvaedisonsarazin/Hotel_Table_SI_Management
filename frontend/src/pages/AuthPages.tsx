import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { MeshBackground } from '../components/layout/MeshBackground'
import { PageWrapper } from '../components/layout/PageWrapper'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { GradientButton } from '../components/ui/Buttons'
import { ErrorNote } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../services/api'

function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <PageWrapper className="flex min-h-screen items-center justify-center">
      <MeshBackground />
      <div className="w-full max-w-md">
        <p className="mb-6 text-center text-xl font-bold text-indigo-800">TableSense</p>
        <GlassCard className="p-6">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-1 mb-5 text-sm text-slate-600">{subtitle}</p>
          {children}
        </GlassCard>
      </div>
    </PageWrapper>
  )
}

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/dashboard" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Log in" subtitle="See your floor, alerts and waitlist.">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
        <AnimatedInput label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <AnimatedInput label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <ErrorNote>{error}</ErrorNote>
        <GradientButton type="submit" disabled={busy}>
          {busy ? 'Logging in…' : 'Log in'}
        </GradientButton>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        New here?{' '}
        <Link to="/register" className="font-semibold text-indigo-800 underline">
          Create an account
        </Link>
      </p>
    </AuthShell>
  )
}

export function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/dashboard" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await register({ email, password, full_name: fullName || undefined })
      navigate('/dashboard')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Try the demo floor or set up your own restaurant.">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
        <AnimatedInput label="Your name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={100} />
        <AnimatedInput label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <AnimatedInput label="Password" type="password" autoComplete="new-password" hint="At least 8 characters." minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required />
        <ErrorNote>{error}</ErrorNote>
        <GradientButton type="submit" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </GradientButton>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-indigo-800 underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}
