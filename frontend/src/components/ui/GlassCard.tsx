import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/format'

interface GlassCardProps {
  children: ReactNode
  className?: string
  /** Lift on hover. Leave off for cards that only hold content, so live boards stay calm. */
  hover?: boolean
}

export function GlassCard({ children, className, hover = false }: GlassCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={hover ? { y: -3 } : undefined}
      className={cn(
        'rounded-2xl border border-slate-200/80 bg-white/80 p-5 shadow-sm backdrop-blur-lg',
        hover && 'transition-shadow hover:shadow-md',
        className,
      )}
    >
      {children}
    </motion.div>
  )
}
