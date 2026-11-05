import { motion, type HTMLMotionProps } from 'framer-motion'
import { cn } from '../../lib/format'

type ButtonProps = HTMLMotionProps<'button'>

const base =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50'

export function GradientButton({ className, type = 'button', ...props }: ButtonProps) {
  return (
    <motion.button
      type={type}
      whileHover={props.disabled ? undefined : { y: -1 }}
      whileTap={props.disabled ? undefined : { scale: 0.98 }}
      className={cn(base, 'bg-linear-to-r from-indigo-700 to-violet-700 text-white shadow-sm', className)}
      {...props}
    />
  )
}

export function SoftButton({ className, type = 'button', ...props }: ButtonProps) {
  return (
    <motion.button
      type={type}
      whileHover={props.disabled ? undefined : { y: -1 }}
      whileTap={props.disabled ? undefined : { scale: 0.98 }}
      className={cn(base, 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50', className)}
      {...props}
    />
  )
}
