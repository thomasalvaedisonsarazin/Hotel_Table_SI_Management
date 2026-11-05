import { PageWrapper } from '../components/layout/PageWrapper'
import { TopBar } from '../components/layout/TopBar'
import { GlassCard } from '../components/ui/GlassCard'
import { useAuth } from '../hooks/useAuth'

export function ProfilePage() {
  const { user } = useAuth()
  return (
    <>
      <TopBar />
      <PageWrapper className="max-w-xl">
        <h1 className="mb-4 text-2xl font-bold">Your profile</h1>
        <GlassCard>
          <dl className="flex flex-col gap-3">
            <div>
              <dt className="text-sm text-slate-600">Name</dt>
              <dd className="font-medium">{user?.full_name || 'Not set'}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-600">Email</dt>
              <dd className="font-medium break-words">{user?.email}</dd>
            </div>
          </dl>
        </GlassCard>
      </PageWrapper>
    </>
  )
}
