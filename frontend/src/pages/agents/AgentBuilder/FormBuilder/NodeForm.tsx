/**
 * NodeForm — dispatcher that renders the right form for the selected outline node.
 *
 * Path patterns:
 *   ""                                          → AgentRootForm
 *   "persona"                                   → PersonaForm
 *   "models"                                    → ModelsForm
 *   "tone"                                      → ToneForm
 *   "global_rules"                              → StringListForm (rules)
 *   "out_of_scope"                              → StringListForm (out of scope)
 *   "tools"                                     → collection landing
 *   "tools[N]"                                  → ToolForm
 *   "conditions"                                → collection landing
 *   "conditions[N]"                             → ConditionForm
 *   "conditions[N].goals"                       → goals collection landing
 *   "conditions[N].goals[M]"                    → GoalForm
 *   "conditions[N].goals[M].slots"              → slots collection landing
 *   "conditions[N].goals[M].slots[K]"           → SlotForm
 *   "conditions[N].goals[M].sequences"          → sequences collection landing
 *   "conditions[N].goals[M].sequences[K]"       → SequenceForm
 *   "handoffs[N]"                               → HandoffForm
 *   "interrupt_triggers[N]"                     → InterruptForm
 *   "sub_agents[N]"                             → SubAgentForm
 */

import { Bot } from "lucide-react"
import type { AgentSchema } from "@/types/agent"
import { AgentRootForm } from "./forms/AgentRootForm"
import { PersonaForm } from "./forms/PersonaForm"
import { ToneForm } from "./forms/ToneForm"
import { ModelsForm } from "./forms/ModelsForm"
import { StringListForm } from "./forms/StringListForm"
import { ToolForm } from "./forms/ToolForm"
import { ConditionForm } from "./forms/ConditionForm"
import { GoalForm } from "./forms/GoalForm"
import { SlotForm } from "./forms/SlotForm"
import { SequenceForm } from "./forms/SequenceForm"
import { HandoffForm } from "./forms/HandoffForm"
import { InterruptForm } from "./forms/InterruptForm"
import { SubAgentForm } from "./forms/SubAgentForm"
import { getNodeAtPath, parsePath, setNodeAtPath, type Path } from "./yamlPath"
import type { Goal, Slot, Sequence, AgentTool, Condition, Handoff, InterruptTrigger, SubAgent, AgentModels } from "@/types/agent"

interface Props {
  schema: AgentSchema
  selectedPath: Path
  onChange: (s: AgentSchema) => void
}

export function NodeForm({ schema, selectedPath, onChange }: Props) {
  const segs = parsePath(selectedPath)
  const node = getNodeAtPath(schema, selectedPath)

  // Helper to mutate the value at the selected path
  const updateAt = (newValue: unknown) => {
    onChange(setNodeAtPath(schema, selectedPath, newValue))
  }

  // ── Root ────────────────────────────────────────────────────────────────────
  if (!selectedPath) {
    return (
      <FormShell title={schema.name || "Untitled Agent"} subtitle="Agent root">
        <AgentRootForm schema={schema} onChange={onChange} />
      </FormShell>
    )
  }

  const lastSeg = segs[segs.length - 1]
  const isCollectionLanding =
    lastSeg && lastSeg.index === undefined &&
    Array.isArray(getNodeAtPath(schema, selectedPath))

  // ── Top-level singletons ───────────────────────────────────────────────────
  if (selectedPath === "persona") {
    return (
      <FormShell title="Persona" subtitle="The agent's role, voice, and background">
        <PersonaForm value={(node as string) ?? ""} onChange={updateAt} />
      </FormShell>
    )
  }
  if (selectedPath === "tone") {
    return (
      <FormShell title="Tone" subtitle="Default communication style">
        <ToneForm value={(node as string) ?? ""} onChange={updateAt} />
      </FormShell>
    )
  }
  if (selectedPath === "models") {
    return (
      <FormShell title="Models" subtitle="LLM models for different stages">
        <ModelsForm value={node as AgentModels | undefined} onChange={updateAt} />
      </FormShell>
    )
  }
  if (selectedPath === "global_rules") {
    return (
      <FormShell title="Global rules" subtitle="Rules that apply across all conditions and goals">
        <StringListForm
          label=""
          value={(node as string[]) ?? []}
          onChange={updateAt}
          placeholder="Always verify the customer's identity before sharing account details"
          addLabel="Add rule"
        />
      </FormShell>
    )
  }
  if (selectedPath === "out_of_scope") {
    return (
      <FormShell title="Out of scope" subtitle="Topics the agent should refuse to address">
        <StringListForm
          label=""
          value={(node as string[]) ?? []}
          onChange={updateAt}
          placeholder="Investment advice, medical diagnoses, legal opinions"
          addLabel="Add topic"
        />
      </FormShell>
    )
  }

  // ── Collection landings ────────────────────────────────────────────────────
  if (selectedPath === "tools" && isCollectionLanding) {
    return <CollectionLanding kind="Tools" count={(node as unknown[]).length} />
  }
  if (selectedPath === "conditions" && isCollectionLanding) {
    return <CollectionLanding kind="Conditions" count={(node as unknown[]).length} />
  }
  if (selectedPath === "handoffs" && isCollectionLanding) {
    return <CollectionLanding kind="Handoffs" count={(node as unknown[]).length} />
  }
  if (selectedPath === "interrupt_triggers" && isCollectionLanding) {
    return <CollectionLanding kind="Interrupt triggers" count={(node as unknown[]).length} />
  }
  if (selectedPath === "sub_agents" && isCollectionLanding) {
    return <CollectionLanding kind="Sub-agents" count={(node as unknown[]).length} />
  }
  if (selectedPath.endsWith(".goals") && isCollectionLanding) {
    return <CollectionLanding kind="Goals" count={(node as unknown[]).length} />
  }
  if (selectedPath.endsWith(".slots") && isCollectionLanding) {
    return <CollectionLanding kind="Slots" count={(node as unknown[]).length} />
  }
  if (selectedPath.endsWith(".sequences") && isCollectionLanding) {
    return <CollectionLanding kind="Sequences" count={(node as unknown[]).length} />
  }
  if (selectedPath.endsWith(".rules") && isCollectionLanding) {
    return (
      <FormShell title="Rules" subtitle="Goal-specific constraints">
        <StringListForm
          label=""
          value={(node as string[]) ?? []}
          onChange={updateAt}
          placeholder="Always confirm the order ID before sharing details"
          addLabel="Add rule"
        />
      </FormShell>
    )
  }

  // ── Item-level forms ───────────────────────────────────────────────────────
  if (segs.length === 1 && segs[0].key === "tools" && segs[0].index !== undefined) {
    return (
      <FormShell title={(node as AgentTool)?.name || "Tool"} subtitle="Tool definition">
        <ToolForm value={node as AgentTool} onChange={updateAt} />
      </FormShell>
    )
  }
  if (segs.length === 1 && segs[0].key === "conditions" && segs[0].index !== undefined) {
    return (
      <FormShell title={(node as Condition)?.name || "Condition"} subtitle="Condition">
        <ConditionForm value={node as Condition} onChange={updateAt} />
      </FormShell>
    )
  }
  if (segs.length === 1 && segs[0].key === "handoffs" && segs[0].index !== undefined) {
    return (
      <FormShell title={(node as Handoff)?.name || "Handoff"} subtitle="Handoff">
        <HandoffForm value={node as Handoff} onChange={updateAt} />
      </FormShell>
    )
  }
  if (segs.length === 1 && segs[0].key === "interrupt_triggers" && segs[0].index !== undefined) {
    return (
      <FormShell title={(node as InterruptTrigger)?.name || "Interrupt"} subtitle="Interrupt trigger">
        <InterruptForm value={node as InterruptTrigger} onChange={updateAt} />
      </FormShell>
    )
  }
  if (segs.length === 1 && segs[0].key === "sub_agents" && segs[0].index !== undefined) {
    return (
      <FormShell title={(node as SubAgent)?.name || "Sub-agent"} subtitle="Sub-agent">
        <SubAgentForm value={node as SubAgent} onChange={updateAt} />
      </FormShell>
    )
  }

  // Goal: conditions[N].goals[M]
  if (
    segs.length === 2 &&
    segs[0].key === "conditions" && segs[0].index !== undefined &&
    segs[1].key === "goals" && segs[1].index !== undefined
  ) {
    return (
      <FormShell title={(node as Goal)?.name || "Goal"} subtitle="Goal">
        <GoalForm value={node as Goal} onChange={updateAt} />
      </FormShell>
    )
  }

  // Slot: conditions[N].goals[M].slots[K]
  if (
    segs.length === 3 &&
    segs[0].key === "conditions" && segs[1].key === "goals" &&
    segs[2].key === "slots" && segs[2].index !== undefined
  ) {
    return (
      <FormShell title={(node as Slot)?.name || "Slot"} subtitle="Slot definition">
        <SlotForm value={node as Slot} onChange={updateAt} />
      </FormShell>
    )
  }

  // Sequence: conditions[N].goals[M].sequences[K]
  if (
    segs.length === 3 &&
    segs[0].key === "conditions" && segs[1].key === "goals" &&
    segs[2].key === "sequences" && segs[2].index !== undefined
  ) {
    return (
      <FormShell title={(node as Sequence)?.name || "Sequence"} subtitle="Sequence">
        <SequenceForm value={node as Sequence} onChange={updateAt} />
      </FormShell>
    )
  }

  // Fallback for unknown paths
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <Bot className="size-10 text-muted-foreground/30 mb-3" />
      <p className="text-sm font-medium">Nothing selected</p>
      <p className="text-xs text-muted-foreground mt-1 max-w-sm">
        Select a node in the outline to edit it. The path{" "}
        <code className="text-foreground">{selectedPath}</code> doesn't have a form yet —
        edit it directly in YAML.
      </p>
    </div>
  )
}

// ── Form shell ────────────────────────────────────────────────────────────────

function FormShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-5 py-3 shrink-0">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-[11px] text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
      <div className="flex-1 overflow-y-auto p-5">{children}</div>
    </div>
  )
}

// ── Collection landing ────────────────────────────────────────────────────────

function CollectionLanding({ kind, count }: { kind: string; count: number }) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <p className="text-sm font-medium">{kind}</p>
      <p className="text-xs text-muted-foreground mt-1">
        {count} {count === 1 ? "item" : "items"} — select one in the outline to edit, or use the{" "}
        <span className="text-foreground">+</span> button to add a new one.
      </p>
    </div>
  )
}
