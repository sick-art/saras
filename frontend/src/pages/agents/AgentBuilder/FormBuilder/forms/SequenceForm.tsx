import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import { StringListField } from "../fields/StringListField"
import type { Sequence } from "@/types/agent"

interface Props {
  value: Sequence
  onChange: (v: Sequence) => void
}

export function SequenceForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Sequence name"
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Locate order"
      />
      <TextAreaField
        label="Description (optional)"
        value={value.description ?? ""}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="Steps the agent should follow to complete this sequence."
        rows={2}
      />
      <StringListField
        label="Steps"
        hint="Ordered steps in plain English. Use @tool: ToolName to reference defined tools."
        items={value.steps ?? []}
        onChange={(steps) => onChange({ ...value, steps })}
        placeholder="@tool: Order Lookup with order_number from slots"
        addLabel="Add step"
      />
    </div>
  )
}
