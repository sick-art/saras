/**
 * TextField — labeled single-line input.
 */

interface Props {
  label?: string
  hint?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: "text" | "url"
}

export function TextField({ label, hint, value, onChange, placeholder, type = "text" }: Props) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-foreground">{label}</label>
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </div>
  )
}
