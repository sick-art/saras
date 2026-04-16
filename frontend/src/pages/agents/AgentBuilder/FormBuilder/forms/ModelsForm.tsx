import { TextField } from "../fields/TextField"
import type { AgentModels } from "@/types/agent"

interface Props {
  value: AgentModels | undefined
  onChange: (v: AgentModels) => void
}

export function ModelsForm({ value, onChange }: Props) {
  const m = value ?? { primary: "" }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        LLM models used at different stages. Use any litellm-supported model name
        (e.g. <code className="text-foreground">claude-sonnet-4-5</code>,{" "}
        <code className="text-foreground">gpt-4o</code>,{" "}
        <code className="text-foreground">claude-haiku-4-5</code>).
      </p>

      <TextField
        label="Primary"
        hint="Main response generator. Required."
        value={m.primary ?? ""}
        onChange={(v) => onChange({ ...m, primary: v })}
        placeholder="claude-sonnet-4-5"
      />
      <TextField
        label="Router"
        hint="Routes user input to the right condition/goal. Usually a fast model."
        value={m.router ?? ""}
        onChange={(v) => onChange({ ...m, router: v })}
        placeholder="claude-haiku-4-5"
      />
      <TextField
        label="Judge"
        hint="LLM-as-judge for evaluations (optional)."
        value={m.judge ?? ""}
        onChange={(v) => onChange({ ...m, judge: v })}
        placeholder="claude-sonnet-4-5"
      />
      <TextField
        label="Fallback"
        hint="Used when the primary model fails or is unavailable."
        value={m.fallback ?? ""}
        onChange={(v) => onChange({ ...m, fallback: v })}
        placeholder="gpt-4o-mini"
      />
    </div>
  )
}
