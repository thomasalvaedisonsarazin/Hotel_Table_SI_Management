import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/format'

export function PageWrapper({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.main
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn('mx-auto w-full max-w-7xl px-4 py-6 sm:px-6', className)}
    >
      {children}
    </motion.main>
  )
}
