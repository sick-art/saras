/**
 * FormBuilder — collapsible block cards for editing agent YAML via form UI.
 *
 * Each major YAML section (Persona, Tone, Global Rules, Conditions, Tools, Handoffs,
 * Interrupt Triggers, Out of Scope) renders as a collapsible card. All edits call
 * store.setYaml() with the updated YAML so YAML stays as single source of truth.
 *
 * This is a structured form layer on top of the YAML — values are derived from
 * parsedSchema; writes go through YAML string manipulation.
 */

import { useState } from "react"
import {
  ChevronDown,
  User,
  MessageSquare,
  ShieldAlert,
  GitBranch,
  Wrench,
  AlertTriangle,
  Ban,
  Plus,
  Trash2,
  Bot,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { useAgentStore } from "@/stores/agent.store"
import type { AgentSchema, Condition, AgentTool, Handoff, InterruptTrigger } from "@/types/agent"
import * as yaml from "js-yaml"

// ── Block registry ─────────────────────────────────────────────────────────────

interface BlockDef {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  count?: (schema: AgentSchema) => number
  component: React.ComponentType<{ schema: AgentSchema; onChange: (s: AgentSchema) => void }>
}

const BLOCKS: BlockDef[] = [
  {
    id: "persona",
    label: "Persona",
    icon: User,
    component: PersonaBlock,
  },
  {
    id: "tone",
    label: "Tone",
    icon: MessageSquare,
    component: ToneBlock,
  },
  {
    id: "global_rules",
    label: "Global Rules",
    icon: ShieldAlert,
    count: (s) => s.global_rules?.length ?? 0,
    component: GlobalRulesBlock,
  },
  {
    id: "conditions",
    label: "Conditions & Goals",
    icon: GitBranch,
    count: (s) => s.conditions?.length ?? 0,
    component: ConditionsBlock,
  },
  {
    id: "tools",
    label: "Tools",
    icon: Wrench,
    count: (s) => s.tools?.length ?? 0,
    component: ToolsBlock,
  },
  {
    id: "handoffs",
    label: "Handoffs",
    icon: GitBranch,
    count: (s) => s.handoffs?.length ?? 0,
    component: HandoffsBlock,
  },
  {
    id: "interrupt_triggers",
    label: "Interrupt Triggers",
    icon: AlertTriangle,
    count: (s) => s.interrupt_triggers?.length ?? 0,
    component: InterruptTriggersBlock,
  },
  {
    id: "out_of_scope",
    label: "Out of Scope",
    icon: Ban,
    count: (s) => s.out_of_scope?.length ?? 0,
    component: OutOfScopeBlock,
  },
]

// ── Root component ─────────────────────────────────────────────────────────────

export function FormBuilder() {
  const { parsedSchema, setYaml, yamlContent } = useAgentStore()

  const schema: AgentSchema = parsedSchema ?? {
    name: "Untitled Agent",
    version: "1.0.0",
    conditions: [],
    tools: [],
    global_rules: [],
    handoffs: [],
    interrupt_triggers: [],
    out_of_scope: [],
  }

  const handleChange = (updated: AgentSchema) => {
    try {
      const raw = yaml.load(yamlContent) as Record<string, unknown> | null
      const newRaw = { ...(raw ?? {}), agent: updated }
      setYaml(yaml.dump(newRaw, { lineWidth: 100 }))
    } catch {
      setYaml(yaml.dump({ agent: updated }, { lineWidth: 100 }))
    }
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-2 p-4">
        {!parsedSchema && (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-10 text-center">
            <Bot className="size-8 text-muted-foreground/40" />
            <p className="text-sm font-medium">No agent loaded</p>
            <p className="text-xs text-muted-foreground max-w-xs">
              Start in the Chat tab to generate a YAML, or write directly in the YAML tab.
            </p>
          </div>
        )}

        {parsedSchema && BLOCKS.map((block) => (
          <BlockCard
            key={block.id}
            block={block}
            schema={schema}
            onChange={handleChange}
          />
        ))}
      </div>
    </ScrollArea>
  )
}

// ── Block card wrapper ─────────────────────────────────────────────────────────

function BlockCard({
  block,
  schema,
  onChange,
}: {
  block: BlockDef
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  const [open, setOpen] = useState(false)
  const count = block.count?.(schema)
  const Icon = block.icon

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-lg border border-border overflow-hidden">
        <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-3 py-2.5 bg-card hover:bg-accent transition-colors text-left">
          <div className="flex items-center gap-2">
            <Icon className="size-4 text-muted-foreground shrink-0" />
            <span className="text-sm font-medium">{block.label}</span>
            {count !== undefined && count > 0 && (
              <Badge variant="secondary">{count}</Badge>
            )}
          </div>
          <ChevronDown
            className={cn(
              "size-4 text-muted-foreground transition-transform shrink-0",
              open && "rotate-180",
            )}
          />
        </CollapsibleTrigger>

        <CollapsibleContent>
          <Separator />
          <div className="p-3 bg-card">
            <block.component schema={schema} onChange={onChange} />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Shared form primitives ─────────────────────────────────────────────────────

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
    />
  )
}

function StringListEditor({
  items,
  onChange,
  placeholder,
}: {
  items: string[]
  onChange: (items: string[]) => void
  placeholder: string
}) {
  const add = () => onChange([...items, ""])
  const update = (i: number, v: string) => onChange(items.map((item, idx) => (idx === i ? v : item)))
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i))

  return (
    <div className="flex flex-col gap-2">
      {items.map((item, i) => (
        <div key={i} className="flex gap-2">
          <input
            value={item}
            onChange={(e) => update(i, e.target.value)}
            placeholder={placeholder}
            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button
            variant="ghost"
            size="icon"
            className="size-7 text-muted-foreground hover:text-destructive"
            onClick={() => remove(i)}
          >
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} className="self-start gap-1 text-xs">
        <Plus data-icon="inline-start" />
        Add
      </Button>
    </div>
  )
}

// ── Block implementations ──────────────────────────────────────────────────────

function PersonaBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs text-muted-foreground">
        Who is this agent? Write as if briefing a new employee.
      </label>
      <TextArea
        value={schema.persona ?? ""}
        onChange={(v) => onChange({ ...schema, persona: v })}
        placeholder="You are a customer support specialist for Acme Corp. You help customers with order tracking, returns, and billing inquiries..."
        rows={4}
      />
    </div>
  )
}

function ToneBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs text-muted-foreground">
        Default communication style — plain English.
      </label>
      <TextArea
        value={schema.tone ?? ""}
        onChange={(v) => onChange({ ...schema, tone: v })}
        placeholder="Friendly, professional, and concise. Empathise with the customer's situation..."
        rows={3}
      />
    </div>
  )
}

function GlobalRulesBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  return (
    <StringListEditor
      items={schema.global_rules ?? []}
      onChange={(rules) => onChange({ ...schema, global_rules: rules })}
      placeholder="Always verify the customer's identity before sharing account details"
    />
  )
}

function OutOfScopeBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  return (
    <StringListEditor
      items={schema.out_of_scope ?? []}
      onChange={(items) => onChange({ ...schema, out_of_scope: items })}
      placeholder="Investment advice, medical diagnoses, legal opinions..."
    />
  )
}

function ConditionsBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  const conditions = schema.conditions ?? []

  const addCondition = () => {
    onChange({
      ...schema,
      conditions: [
        ...conditions,
        { name: "New Condition", description: "", goals: [] },
      ],
    })
  }

  const removeCondition = (i: number) => {
    onChange({ ...schema, conditions: conditions.filter((_, idx) => idx !== i) })
  }

  const updateCondition = (i: number, c: Condition) => {
    onChange({ ...schema, conditions: conditions.map((x, idx) => (idx === i ? c : x)) })
  }

  return (
    <div className="flex flex-col gap-3">
      {conditions.map((cond, i) => (
        <div key={i} className="rounded-md border border-border p-2.5 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <input
              value={cond.name}
              onChange={(e) => updateCondition(i, { ...cond, name: e.target.value })}
              className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-border focus:outline-none pb-0.5"
              placeholder="Condition name"
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground hover:text-destructive"
              onClick={() => removeCondition(i)}
            >
              <Trash2 />
            </Button>
          </div>
          <TextArea
            value={cond.description}
            onChange={(v) => updateCondition(i, { ...cond, description: v })}
            placeholder="When does this condition apply? Plain English."
            rows={2}
          />
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <GitBranch className="size-3" />
            {cond.goals?.length ?? 0} goal{(cond.goals?.length ?? 0) !== 1 ? "s" : ""} — edit in YAML or Chat for full goal config
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addCondition} className="self-start gap-1 text-xs">
        <Plus data-icon="inline-start" />
        Add Condition
      </Button>
    </div>
  )
}

function ToolsBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  const tools = schema.tools ?? []

  const addTool = () => {
    const newTool: AgentTool = {
      name: "New Tool",
      type: "LookupTool",
      description: "",
    }
    onChange({ ...schema, tools: [...tools, newTool] })
  }

  const removeTool = (i: number) => {
    onChange({ ...schema, tools: tools.filter((_, idx) => idx !== i) })
  }

  const updateTool = (i: number, t: AgentTool) => {
    onChange({ ...schema, tools: tools.map((x, idx) => (idx === i ? t : x)) })
  }

  return (
    <div className="flex flex-col gap-3">
      {tools.map((tool, i) => (
        <div key={i} className="rounded-md border border-border p-2.5 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <input
              value={tool.name}
              onChange={(e) => updateTool(i, { ...tool, name: e.target.value })}
              className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-border focus:outline-none pb-0.5"
              placeholder="Tool name (human-readable)"
            />
            <select
              value={tool.type}
              onChange={(e) => updateTool(i, { ...tool, type: e.target.value as AgentTool["type"] })}
              className="rounded border border-input bg-background px-2 py-0.5 text-xs"
            >
              <option value="LookupTool">Lookup</option>
              <option value="ActionTool">Action</option>
              <option value="KnowledgeTool">Knowledge</option>
            </select>
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground hover:text-destructive"
              onClick={() => removeTool(i)}
            >
              <Trash2 />
            </Button>
          </div>
          <TextArea
            value={tool.description}
            onChange={(v) => updateTool(i, { ...tool, description: v })}
            placeholder="What does this tool do?"
            rows={2}
          />
          {(tool.type === "LookupTool" || tool.type === "ActionTool") && (
            <input
              value={tool.endpoint ?? ""}
              onChange={(e) => updateTool(i, { ...tool, endpoint: e.target.value })}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs text-muted-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="Endpoint URL (optional)"
            />
          )}
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={addTool} className="self-start gap-1 text-xs">
        <Plus data-icon="inline-start" />
        Add Tool
      </Button>
    </div>
  )
}

function HandoffsBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  const handoffs = schema.handoffs ?? []

  const add = () => {
    onChange({
      ...schema,
      handoffs: [...handoffs, { name: "New Handoff", description: "", target: "Human Support Queue" }],
    })
  }

  const remove = (i: number) =>
    onChange({ ...schema, handoffs: handoffs.filter((_, idx) => idx !== i) })

  const update = (i: number, h: Handoff) =>
    onChange({ ...schema, handoffs: handoffs.map((x, idx) => (idx === i ? h : x)) })

  return (
    <div className="flex flex-col gap-3">
      {handoffs.map((h, i) => (
        <div key={i} className="rounded-md border border-border p-2.5 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <input
              value={h.name}
              onChange={(e) => update(i, { ...h, name: e.target.value })}
              className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-border focus:outline-none pb-0.5"
              placeholder="Handoff name"
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground hover:text-destructive"
              onClick={() => remove(i)}
            >
              <Trash2 />
            </Button>
          </div>
          <TextArea
            value={h.description}
            onChange={(v) => update(i, { ...h, description: v })}
            placeholder="When should this handoff happen? Plain English."
            rows={2}
          />
          <input
            value={h.target}
            onChange={(e) => update(i, { ...h, target: e.target.value })}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="Target: agent name or 'Human Support Queue'"
          />
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} className="self-start gap-1 text-xs">
        <Plus data-icon="inline-start" />
        Add Handoff
      </Button>
    </div>
  )
}

function InterruptTriggersBlock({
  schema,
  onChange,
}: {
  schema: AgentSchema
  onChange: (s: AgentSchema) => void
}) {
  const triggers = schema.interrupt_triggers ?? []

  const add = () => {
    const t: InterruptTrigger = { name: "New Trigger", description: "" }
    onChange({ ...schema, interrupt_triggers: [...triggers, t] })
  }

  const remove = (i: number) =>
    onChange({ ...schema, interrupt_triggers: triggers.filter((_, idx) => idx !== i) })

  const update = (i: number, t: InterruptTrigger) =>
    onChange({ ...schema, interrupt_triggers: triggers.map((x, idx) => (idx === i ? t : x)) })

  return (
    <div className="flex flex-col gap-3">
      {triggers.map((t, i) => (
        <div key={i} className="rounded-md border border-border p-2.5 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <input
              value={t.name}
              onChange={(e) => update(i, { ...t, name: e.target.value })}
              className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-border focus:outline-none pb-0.5"
              placeholder="Trigger name"
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-6 text-muted-foreground hover:text-destructive"
              onClick={() => remove(i)}
            >
              <Trash2 />
            </Button>
          </div>
          <TextArea
            value={t.description}
            onChange={(v) => update(i, { ...t, description: v })}
            placeholder="When should this interrupt fire? Checked before every response."
            rows={2}
          />
          <TextArea
            value={t.action ?? ""}
            onChange={(v) => update(i, { ...t, action: v })}
            placeholder="What action should the agent take? (optional)"
            rows={2}
          />
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} className="self-start gap-1 text-xs">
        <Plus data-icon="inline-start" />
        Add Trigger
      </Button>
    </div>
  )
}
