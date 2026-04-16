import { TextField } from "../fields/TextField"
import type { SubAgent } from "@/types/agent"

interface Props {
  value: SubAgent
  onChange: (v: SubAgent) => void
}

export function SubAgentForm({ value, onChange }: Props) {
  return (
    <div className="space-y-4">
      <TextField
        label="Sub-agent name"
        hint="Used as the handoff target."
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Billing Specialist"
      />
      <TextField
        label="Reference"
        hint="Path to the sub-agent's YAML file. Use this OR an inline definition."
        value={value.ref ?? ""}
        onChange={(v) => onChange({ ...value, ref: v })}
        placeholder="agents/billing_specialist.yaml"
      />
      {value.inline && (
        <p className="text-[11px] text-muted-foreground italic">
          This sub-agent has an inline definition — edit in YAML to modify nested
          schema. Inline editing in form is not yet supported.
        </p>
      )}
    </div>
  )
}
