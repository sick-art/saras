import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import type { AgentSchema } from "@/types/agent"

interface Props {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}

export function AgentRootForm({ schema, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Agent name"
        value={schema.name ?? ""}
        onChange={(v) => onChange({ ...schema, name: v })}
        placeholder="Customer Support Agent"
      />
      <TextField
        label="Version"
        hint="Semantic version (e.g. 1.0.0). Used to track agent changes."
        value={schema.version ?? ""}
        onChange={(v) => onChange({ ...schema, version: v })}
        placeholder="1.0.0"
      />
      <TextAreaField
        label="Description"
        hint="What this agent does, in one or two sentences."
        value={schema.description ?? ""}
        onChange={(v) => onChange({ ...schema, description: v })}
        placeholder="Handles customer support inquiries about orders, returns, and billing."
        rows={2}
      />
    </div>
  )
}
