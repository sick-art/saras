/**
 * CheckboxField — labeled boolean toggle.
 */

interface Props {
  label: string
  hint?: string
  checked: boolean
  onChange: (v: boolean) => void
}

export function CheckboxField({ label, hint, checked, onChange }: Props) {
  return (
    <label className="flex items-start gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 rounded border-input cursor-pointer"
      />
      <div className="flex flex-col gap-0.5">
        <span className="text-xs font-medium text-foreground">{label}</span>
        {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
      </div>
    </label>
  )
}
