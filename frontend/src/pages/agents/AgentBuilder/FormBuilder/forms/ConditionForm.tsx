import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import type { Condition } from "@/types/agent"

interface Props {
  value: Condition
  onChange: (v: Condition) => void
}

export function ConditionForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Condition name"
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Order tracking inquiry"
      />
      <TextAreaField
        label="Description"
        hint="When does this condition apply? Plain English. The router LLM uses this to decide which condition matches the user's input."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="The user is asking about the status or location of their order."
        rows={3}
      />
      <p className="text-[11px] text-muted-foreground italic">
        {value.goals?.length ?? 0} goal{(value.goals?.length ?? 0) === 1 ? "" : "s"} —
        select a goal in the outline to edit its slots, sequences, and rules.
      </p>
    </div>
  )
}
