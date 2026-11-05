interface ToggleProps {
  label: string
  checked: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
}

export function Toggle({ label, checked, disabled, onChange }: ToggleProps) {
  return (
    <label className={`flex min-h-11 items-center gap-3 text-sm ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5 shrink-0 accent-indigo-700"
      />
      <span>{label}</span>
    </label>
  )
}
