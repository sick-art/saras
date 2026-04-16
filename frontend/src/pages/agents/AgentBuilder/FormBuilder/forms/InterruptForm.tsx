import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import type { InterruptTrigger } from "@/types/agent"

interface Props {
  value: InterruptTrigger
  onChange: (v: InterruptTrigger) => void
}

export function InterruptForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Trigger name"
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Profanity detected"
      />
      <TextAreaField
        label="Description"
        hint="When should this interrupt fire? Checked before every response."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="The user's message contains profanity, slurs, or abusive language directed at the agent or others."
        rows={3}
      />
      <TextAreaField
        label="Action (optional)"
        hint="What action should the agent take when triggered? Plain English."
        value={value.action ?? ""}
        onChange={(v) => onChange({ ...value, action: v })}
        placeholder="Politely warn the user that this language is unacceptable. Continue helping if they apologise."
        rows={2}
      />
    </div>
  )
}
