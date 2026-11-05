import { motion, type HTMLMotionProps } from 'framer-motion'
import { useId } from 'react'
import { cn } from '../../lib/format'

interface AnimatedInputProps extends HTMLMotionProps<'input'> {
  label: string
  error?: string
  hint?: string
}

export function AnimatedInput({ label, error, hint, className, id, ...props }: AnimatedInputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  return (
    <div className={className}>
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <motion.input
        id={inputId}
        whileFocus={{ scale: 1.005 }}
        aria-invalid={error ? true : undefined}
        className={cn(
          'min-h-11 w-full rounded-xl border-2 bg-white px-3 py-2 outline-none focus:border-indigo-600',
          error ? 'border-red-600' : 'border-slate-200',
        )}
        {...props}
      />
      {hint && !error && <p className="mt-1 text-xs text-slate-600">{hint}</p>}
      {error && <p className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  )
}
