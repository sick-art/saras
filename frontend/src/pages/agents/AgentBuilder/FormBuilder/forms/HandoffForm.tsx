import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import type { Handoff } from "@/types/agent"

interface Props {
  value: Handoff
  onChange: (v: Handoff) => void
}

export function HandoffForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Handoff name"
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Escalate to senior agent"
      />
      <TextAreaField
        label="Description"
        hint="When should this handoff happen? Plain English condition."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="The user's issue is complex or they have asked to speak with a manager."
        rows={3}
      />
      <TextField
        label="Target"
        hint="Sub-agent name or 'Human Support Queue'."
        value={value.target}
        onChange={(v) => onChange({ ...value, target: v })}
        placeholder="Human Support Queue"
      />
      <TextAreaField
        label="Context to pass (optional)"
        hint="What context should travel with the handoff? Plain English."
        value={value.context_to_pass ?? ""}
        onChange={(v) => onChange({ ...value, context_to_pass: v })}
        placeholder="Order number, customer email, summary of the issue, what's been tried."
        rows={2}
      />
    </div>
  )
}
