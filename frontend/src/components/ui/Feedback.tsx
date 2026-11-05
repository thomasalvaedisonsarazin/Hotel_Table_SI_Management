import type { ReactNode } from 'react'

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
      {children}
    </p>
  )
}

export function LoadingNote({ label = 'Loading…' }: { label?: string }) {
  return (
    <p role="status" className="py-10 text-center text-slate-600">
      {label}
    </p>
  )
}

export function SampleDataBadge() {
  return (
    <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
      Sample data
    </span>
  )
}
