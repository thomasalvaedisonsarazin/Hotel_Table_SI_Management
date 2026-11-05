import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'
import { TopBar } from '../components/layout/TopBar'
import { AnimatedInput } from '../components/ui/AnimatedInput'
import { AnimatedList } from '../components/ui/AnimatedList'
import { GradientButton, SoftButton } from '../components/ui/Buttons'
import { ErrorNote, LoadingNote, SampleDataBadge } from '../components/ui/Feedback'
import { GlassCard } from '../components/ui/GlassCard'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../services/api'
import { restaurantService } from '../services/restaurantService'

export function DashboardPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const restaurants = useQuery({ queryKey: ['restaurants'], queryFn: restaurantService.list })

  const create = useMutation({
    mutationFn: () => restaurantService.create(name.trim()),
    onSuccess: (restaurant) => {
      void queryClient.invalidateQueries({ queryKey: ['restaurants'] })
      navigate(`/r/${restaurant.id}/setup`)
    },
  })
  const demo = useMutation({
    mutationFn: restaurantService.createDemo,
    onSuccess: (restaurant) => {
      void queryClient.invalidateQueries({ queryKey: ['restaurants'] })
      navigate(`/r/${restaurant.id}/floor`)
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate()
  }

  // Staff work at one restaurant, so skip the list and take them straight to the floor.
  if (user?.is_staff_account && restaurants.data?.length === 1) {
    return <Navigate to={`/r/${restaurants.data[0].id}/floor`} replace />
  }

  return (
    <>
      <TopBar />
      <PageWrapper className="max-w-3xl">
        <h1 className="text-2xl font-bold">Your restaurants</h1>

        {restaurants.isLoading && <LoadingNote />}
        {restaurants.isError && <ErrorNote>{errorMessage(restaurants.error)}</ErrorNote>}

        {restaurants.data && restaurants.data.length > 0 && (
          <AnimatedList className="mt-4 flex flex-col gap-3">
            {restaurants.data.map((restaurant) => (
              <Link key={restaurant.id} to={`/r/${restaurant.id}/floor`} className="block rounded-2xl">
                <GlassCard hover className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      <span className="break-words">{restaurant.name}</span>
                      {restaurant.is_demo && <SampleDataBadge />}
                    </p>
                    <p className="text-sm text-slate-600">{restaurant.timezone}</p>
                  </div>
                  <ChevronRight className="shrink-0 text-slate-500" aria-hidden="true" />
                </GlassCard>
              </Link>
            ))}
          </AnimatedList>
        )}

        {restaurants.data?.length === 0 && (
          <p className="mt-2 text-slate-600">
            {user?.is_staff_account
              ? 'Your account is not linked to a restaurant right now. Ask your manager.'
              : 'Add your restaurant, or open the demo to see the live floor working with simulated guests.'}
          </p>
        )}

        {!user?.is_staff_account && <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <GlassCard>
            <h2 className="font-semibold">Add a restaurant</h2>
            <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
              <AnimatedInput label="Restaurant name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
              <GradientButton type="submit" disabled={create.isPending}>
                Add restaurant
              </GradientButton>
              {create.isError && <ErrorNote>{errorMessage(create.error)}</ErrorNote>}
            </form>
          </GlassCard>
          <GlassCard className="flex flex-col">
            <h2 className="font-semibold">See it working</h2>
            <p className="mt-2 flex-1 text-sm text-slate-600">
              A demo restaurant with simulated guests, alerts and four weeks of sample analytics.
            </p>
            <SoftButton className="mt-3" disabled={demo.isPending} onClick={() => demo.mutate()}>
              {demo.isPending ? 'Preparing demo…' : 'Open the demo'}
            </SoftButton>
            {demo.isError && <ErrorNote>{errorMessage(demo.error)}</ErrorNote>}
          </GlassCard>
        </div>}
      </PageWrapper>
    </>
  )
}
