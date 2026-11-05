import { Link } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'

export function NotFoundPage() {
  return (
    <PageWrapper className="text-center">
      <h1 className="mt-16 text-2xl font-bold">Page not found</h1>
      <Link to="/dashboard" className="mt-4 inline-block font-semibold text-indigo-800 underline">
        Back to your restaurants
      </Link>
    </PageWrapper>
  )
}
