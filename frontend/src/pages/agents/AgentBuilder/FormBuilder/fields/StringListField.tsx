/**
 * StringListField — labeled add/remove list of single-line strings.
 */

import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"

interface Props {
  label?: string
  hint?: string
  items: string[]
  onChange: (items: string[]) => void
  placeholder: string
  addLabel?: string
}

export function StringListField({
  label, hint, items, onChange, placeholder, addLabel = "Add",
}: Props) {
  const add = () => onChange([...items, ""])
  const update = (i: number, v: string) => onChange(items.map((it, idx) => (idx === i ? v : it)))
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-foreground">{label}</label>
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      <div className="flex flex-col gap-1.5">
        {items.map((item, i) => (
          <div key={i} className="flex gap-1.5">
            <input
              value={item}
              onChange={(e) => update(i, e.target.value)}
              placeholder={placeholder}
              className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-7 text-muted-foreground hover:text-destructive"
              onClick={() => remove(i)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={add} className="self-start gap-1 text-xs">
          <Plus data-icon="inline-start" />
          {addLabel}
        </Button>
      </div>
    </div>
  )
}
