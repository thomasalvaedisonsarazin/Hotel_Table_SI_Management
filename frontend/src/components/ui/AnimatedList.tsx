import { motion } from 'framer-motion'
import { Children, isValidElement, type ReactNode } from 'react'

export function AnimatedList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
    >
      {Children.toArray(children).map((child, index) => (
        <motion.div
          key={isValidElement(child) && child.key !== null ? child.key : index}
          variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
        >
          {child}
        </motion.div>
      ))}
    </motion.div>
  )
}
