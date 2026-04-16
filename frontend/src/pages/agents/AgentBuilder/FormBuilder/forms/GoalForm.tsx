import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import { StringListField } from "../fields/StringListField"
import { ToolMultiSelect } from "../fields/ToolMultiSelect"
import type { Goal } from "@/types/agent"

interface Props {
  value: Goal
  onChange: (v: Goal) => void
}

export function GoalForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Goal name"
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Locate order"
      />
      <TextAreaField
        label="Description"
        hint="What this goal accomplishes for the user."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="Help the user find their order and provide tracking details."
        rows={3}
      />
      <TextAreaField
        label="Tone override (optional)"
        hint="Use a different tone for this goal than the agent default. Leave blank to inherit."
        value={value.tone ?? ""}
        onChange={(v) => onChange({ ...value, tone: v })}
        placeholder="Reassuring and patient — customers asking about lost orders are often frustrated."
        rows={2}
      />
      <ToolMultiSelect
        label="Tools used"
        hint="Tools available to this goal. Selected from agent-level tools."
        selected={value.tools ?? []}
        onChange={(tools) => onChange({ ...value, tools })}
      />
      <StringListField
        label="Rules"
        hint="Goal-specific constraints, in plain English."
        items={value.rules ?? []}
        onChange={(rules) => onChange({ ...value, rules })}
        placeholder="Always confirm the order ID before sharing details"
        addLabel="Add rule"
      />
      <p className="text-[11px] text-muted-foreground italic">
        Slots and sequences for this goal — select them in the outline to edit.
      </p>
    </div>
  )
}
