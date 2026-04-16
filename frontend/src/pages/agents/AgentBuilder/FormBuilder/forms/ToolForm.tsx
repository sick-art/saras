import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { TextField } from "../fields/TextField"
import { TextAreaField } from "../fields/TextAreaField"
import { SelectField } from "../fields/SelectField"
import { CheckboxField } from "../fields/CheckboxField"
import type { AgentTool, ToolInput } from "@/types/agent"

interface Props {
  value: AgentTool
  onChange: (v: AgentTool) => void
}

export function ToolForm({ value, onChange }: Props) {
  const updateInput = (i: number, input: ToolInput) => {
    onChange({
      ...value,
      inputs: (value.inputs ?? []).map((x, idx) => idx === i ? input : x),
    })
  }
  const addInput = () => {
    onChange({
      ...value,
      inputs: [...(value.inputs ?? []), { name: "", description: "", required: false }],
    })
  }
  const removeInput = (i: number) => {
    onChange({ ...value, inputs: (value.inputs ?? []).filter((_, idx) => idx !== i) })
  }

  const isHttp = value.type === "LookupTool" || value.type === "ActionTool"
  const isKnowledge = value.type === "KnowledgeTool"

  return (
    <div className="space-y-4">
      <TextField
        label="Tool name"
        hint="Human-readable name. Goals reference tools by this name."
        value={value.name}
        onChange={(v) => onChange({ ...value, name: v })}
        placeholder="Order Lookup"
      />

      <SelectField
        label="Type"
        hint="LookupTool fetches data, ActionTool performs an action with side effects, KnowledgeTool searches a corpus."
        value={value.type}
        onChange={(v) => onChange({ ...value, type: v as AgentTool["type"] })}
        options={[
          { value: "LookupTool", label: "Lookup" },
          { value: "ActionTool", label: "Action" },
          { value: "KnowledgeTool", label: "Knowledge" },
        ]}
      />

      <TextAreaField
        label="Description"
        hint="What does this tool do? The agent uses this to decide when to call it."
        value={value.description}
        onChange={(v) => onChange({ ...value, description: v })}
        placeholder="Looks up order details by order ID."
        rows={2}
      />

      {isHttp && (
        <>
          <TextField
            label="Endpoint"
            hint="Full HTTPS URL. Can include path parameters like {order_id}."
            value={value.endpoint ?? ""}
            onChange={(v) => onChange({ ...value, endpoint: v })}
            placeholder="https://api.example.com/orders/{order_id}"
            type="url"
          />
          <TextField
            label="Auth"
            hint="Auth method (e.g. 'bearer:env:API_KEY')."
            value={value.auth ?? ""}
            onChange={(v) => onChange({ ...value, auth: v })}
            placeholder="bearer:env:API_KEY"
          />
        </>
      )}

      {value.type === "ActionTool" && (
        <CheckboxField
          label="Confirmation required"
          hint="If enabled, the agent must confirm with the user before invoking this tool."
          checked={value.confirmation_required ?? false}
          onChange={(v) => onChange({ ...value, confirmation_required: v })}
        />
      )}

      {isKnowledge && (
        <>
          <TextField
            label="Source"
            hint="Knowledge source identifier."
            value={value.source ?? ""}
            onChange={(v) => onChange({ ...value, source: v })}
            placeholder="docs"
          />
          <TextField
            label="Collection"
            hint="Specific collection within the source."
            value={value.collection ?? ""}
            onChange={(v) => onChange({ ...value, collection: v })}
            placeholder="customer-faq"
          />
        </>
      )}

      {/* Inputs */}
      {(isHttp) && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-foreground">Inputs</label>
          <p className="text-[11px] text-muted-foreground">
            Parameters the agent must collect (or extract) before calling this tool.
          </p>
          {(value.inputs ?? []).map((inp, i) => (
            <div key={i} className="rounded-md border border-border p-2 flex flex-col gap-2">
              <div className="flex gap-2 items-center">
                <input
                  value={inp.name}
                  onChange={(e) => updateInput(i, { ...inp, name: e.target.value })}
                  placeholder="input_name"
                  className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs"
                />
                <label className="flex items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={inp.required}
                    onChange={(e) => updateInput(i, { ...inp, required: e.target.checked })}
                  />
                  required
                </label>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 text-muted-foreground hover:text-destructive"
                  onClick={() => removeInput(i)}
                >
                  <Trash2 />
                </Button>
              </div>
              <input
                value={inp.description}
                onChange={(e) => updateInput(i, { ...inp, description: e.target.value })}
                placeholder="Description"
                className="rounded-md border border-input bg-background px-2 py-1 text-xs"
              />
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={addInput} className="self-start gap-1 text-xs">
            <Plus data-icon="inline-start" />
            Add input
          </Button>
        </div>
      )}

      <TextAreaField
        label="On failure"
        hint="What should the agent do if this tool call fails? (e.g. 'apologise and offer to escalate')"
        value={value.on_failure ?? ""}
        onChange={(v) => onChange({ ...value, on_failure: v })}
        placeholder="Apologise and offer to escalate to a human agent."
        rows={2}
      />

      <TextAreaField
        label="On empty result"
        hint="What should the agent do if the tool returns no results?"
        value={value.on_empty_result ?? ""}
        onChange={(v) => onChange({ ...value, on_empty_result: v })}
        placeholder="Tell the user we couldn't find any matching records and ask for verification."
        rows={2}
      />
    </div>
  )
}
