/**
 * TextAreaField — labeled multi-line input.
 */

interface Props {
  label?: string
  hint?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
}

export function TextAreaField({ label, hint, value, onChange, placeholder, rows = 3 }: Props) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-foreground">{label}</label>
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </div>
  )
}
