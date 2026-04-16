/**
 * SelectField — labeled native select.
 */

interface Option {
  value: string
  label: string
}

interface Props {
  label?: string
  hint?: string
  value: string
  onChange: (v: string) => void
  options: Option[]
}

export function SelectField({ label, hint, value, onChange, options }: Props) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-foreground">{label}</label>
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  )
}
