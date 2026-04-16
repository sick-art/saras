import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import { CheckboxField } from "../fields/CheckboxField"
import type { Slot } from "@/types/agent"

interface Props {
  value: Slot
  onChange: (v: Slot) => void
}

export function SlotForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Slot name"
        hint="Identifier used in tool input mappings (snake_case recommended)."
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="order_number"
      />
      <TextAreaField
        label="Description"
        hint="What this slot represents."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="The unique 8-digit order number printed on the receipt."
        rows={2}
      />
      <CheckboxField
        label="Required"
        hint="If enabled, the agent will not proceed until this slot is filled."
        checked={value.required}
        onChange={(v) => onChange({ ...value, required: v })}
      />
      <TextAreaField
        label="Ask if missing"
        hint="The exact question (or instruction) the agent should use to gather this slot when missing."
        value={value.ask_if_missing ?? ""}
        onChange={(v) => onChange({ ...value, ask_if_missing: v })}
        placeholder="What's the order number on your receipt? It's usually 8 digits."
        rows={2}
      />
    </div>
  )
}
