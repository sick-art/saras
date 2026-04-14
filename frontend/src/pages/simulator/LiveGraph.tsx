/**
 * LiveGraph — right panel of SimulatorLayout.
 *
 * React Flow canvas mirroring the compiled agent's condition/goal graph.
 * Nodes pulse and highlight in real time as WebSocket span events arrive.
 *
 * Span → node ID mapping (resolved upstream in SimulatorLayout):
 *   router_decision    → root pulse + active condition + active goal
 *   llm_call_start/end → root pulse
 *   tool_call          → tool node active
 *   slot_fill          → goal node active (from last router decision)
 *   interrupt_triggered → interrupt node active
 *   handoff_triggered  → handoff node active
 *
 * Node IDs are deterministic (same algorithm as GraphBuilder):
 *   root, cond-{i}, goal-{i}-{j}, tool-{i}, handoff-{i}, interrupt-{i}
 *
 * Visual treatment:
 *   "active"  → filled background + stronger border (state is resolved)
 *   "pulse"   → ring animation (computation in flight)
 *   (none)    → muted base style
 */

import { useMemo } from "react"
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
  ReactFlowProvider,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { Bot, GitBranch, Target, Wrench, ArrowRightLeft, Zap } from "lucide-react"
import type { AgentSchema } from "@/types/agent"
import type { NodeHighlights } from "./SimulatorLayout"

// ── Node styles ────────────────────────────────────────────────────────────────

const BASE = {
  root:      { bg: "bg-primary/10",       border: "border-primary/40",      text: "text-primary" },
  condition: { bg: "bg-blue-500/10",      border: "border-blue-500/40",     text: "text-blue-700 dark:text-blue-400" },
  goal:      { bg: "bg-emerald-500/10",   border: "border-emerald-500/40",  text: "text-emerald-700 dark:text-emerald-400" },
  tool:      { bg: "bg-amber-500/10",     border: "border-amber-500/40",    text: "text-amber-700 dark:text-amber-400" },
  handoff:   { bg: "bg-purple-500/10",    border: "border-purple-500/40",   text: "text-purple-700 dark:text-purple-400" },
  interrupt: { bg: "bg-red-500/10",       border: "border-red-500/40",      text: "text-red-700 dark:text-red-400" },
} as const

const ACTIVE = {
  root:      { bg: "bg-primary",          border: "border-primary",         text: "text-primary-foreground" },
  condition: { bg: "bg-blue-500/25",      border: "border-blue-500",        text: "text-blue-800 dark:text-blue-300" },
  goal:      { bg: "bg-emerald-500/25",   border: "border-emerald-500",     text: "text-emerald-800 dark:text-emerald-300" },
  tool:      { bg: "bg-amber-500/25",     border: "border-amber-500",       text: "text-amber-800 dark:text-amber-300" },
  handoff:   { bg: "bg-purple-500/25",    border: "border-purple-500",      text: "text-purple-800 dark:text-purple-300" },
  interrupt: { bg: "bg-red-500/25",       border: "border-red-500",         text: "text-red-800 dark:text-red-300" },
} as const

type NodeKind = keyof typeof BASE

// ── AgentNode (with highlight support) ────────────────────────────────────────

function AgentNode({ data }: NodeProps) {
  const { kind, label, description, icon: Icon, highlight } = data as {
    kind: NodeKind
    label: string
    description?: string
    icon: React.ComponentType<{ className?: string }>
    highlight: "pulse" | "active" | null
  }

  const style = highlight ? ACTIVE[kind] : BASE[kind]
  const ring  = highlight === "pulse"
    ? "ring-2 ring-primary/50 ring-offset-1 ring-offset-background"
    : ""

  return (
    <div
      className={`rounded-lg border px-3 py-2 shadow-sm min-w-[140px] max-w-[200px] transition-all duration-200 ${style.bg} ${style.border} ${ring}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-border" />
      <div className="flex items-center gap-1.5">
        <Icon className={`size-3.5 shrink-0 ${style.text}`} />
        <span className={`text-xs font-medium truncate ${style.text}`}>{label}</span>
      </div>
      {description && (
        <p className="mt-1 text-[10px] text-muted-foreground line-clamp-2 leading-relaxed">
          {description}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-border" />
    </div>
  )
}

const nodeTypes = { agent: AgentNode }

// ── Graph layout ───────────────────────────────────────────────────────────────

const H_GAP = 220
const V_GAP = 120

function buildGraph(
  schema: AgentSchema | null,
  highlights: NodeHighlights,
): { nodes: Node[]; edges: Edge[] } {
  if (!schema) return { nodes: [], edges: [] }

  const nodes: Node[] = []
  const edges: Edge[] = []

  const addNode = (
    id: string, x: number, y: number,
    kind: NodeKind, label: string, description?: string,
    Icon: React.ComponentType<{ className?: string }> = Bot,
  ) => {
    nodes.push({
      id, type: "agent", position: { x, y },
      data: {
        kind, label, description, icon: Icon,
        highlight: highlights.get(id) ?? null,
      },
    })
  }

  const addEdge = (source: string, target: string, dashed = false) => {
    edges.push({
      id: `${source}→${target}`,
      source, target,
      animated: dashed,
      style: dashed
        ? { strokeDasharray: "4 2", stroke: "var(--border)" }
        : { stroke: "var(--border)" },
    })
  }

  // Root
  addNode("root", 0, 0, "root", schema.name || "Agent", schema.persona?.slice(0, 60), Bot)

  // Conditions + goals
  const conditions = schema.conditions ?? []
  const condW = conditions.length * H_GAP
  const condX0 = -(condW / 2) + H_GAP / 2

  conditions.forEach((cond, ci) => {
    const cx = condX0 + ci * H_GAP
    const condId = `cond-${ci}`
    addNode(condId, cx, V_GAP, "condition", cond.name, cond.description, GitBranch)
    addEdge("root", condId)

    const goals = cond.goals ?? []
    const goalW = goals.length * (H_GAP * 0.8)
    const goalX0 = cx - goalW / 2 + (H_GAP * 0.8) / 2
    goals.forEach((goal, gi) => {
      const goalId = `goal-${ci}-${gi}`
      addNode(goalId, goalX0 + gi * (H_GAP * 0.8), V_GAP * 2, "goal", goal.name, goal.description, Target)
      addEdge(condId, goalId)
    })
  })

  // Tools
  const tools = schema.tools ?? []
  tools.forEach((tool, ti) => {
    const toolId = `tool-${ti}`
    const tx = condX0 + ti * (H_GAP * 0.75) - H_GAP * 0.5
    addNode(toolId, tx, V_GAP * 3, "tool", tool.name, `${tool.type}: ${tool.description?.slice(0, 40)}`, Wrench)
    conditions.forEach((cond, ci) => {
      cond.goals?.forEach((goal, gi) => {
        if (goal.tools?.includes(tool.name)) addEdge(`goal-${ci}-${gi}`, toolId, true)
      })
    })
  })

  // Handoffs
  const handoffs = schema.handoffs ?? []
  handoffs.forEach((h, hi) => {
    const hId = `handoff-${hi}`
    addNode(hId, H_GAP * 1.5 + hi * H_GAP, 0, "handoff", h.name, `→ ${h.target}`, ArrowRightLeft)
    addEdge("root", hId, true)
  })

  // Interrupt triggers
  const interrupts = schema.interrupt_triggers ?? []
  interrupts.forEach((t, ti) => {
    const iId = `interrupt-${ti}`
    addNode(iId, -(H_GAP * 1.5) - ti * H_GAP, 0, "interrupt", t.name, t.description, Zap)
    addEdge("root", iId, true)
  })

  return { nodes, edges }
}

// ── MiniMap color helper ───────────────────────────────────────────────────────

const MINIMAP_COLORS: Record<NodeKind, string> = {
  root:      "hsl(var(--primary))",
  condition: "#3b82f6",
  goal:      "#10b981",
  tool:      "#f59e0b",
  handoff:   "#a855f7",
  interrupt: "#ef4444",
}

// ── Legend ─────────────────────────────────────────────────────────────────────

const LEGEND_ITEMS: Array<{ kind: NodeKind; label: string }> = [
  { kind: "root",      label: "Agent" },
  { kind: "condition", label: "Condition" },
  { kind: "goal",      label: "Goal" },
  { kind: "tool",      label: "Tool" },
  { kind: "handoff",   label: "Handoff" },
  { kind: "interrupt", label: "Interrupt" },
]

function Legend() {
  return (
    <div className="absolute bottom-2 left-2 z-10 flex flex-col gap-1 rounded-lg border border-border bg-card/90 px-2.5 py-2 backdrop-blur-sm">
      {LEGEND_ITEMS.map(({ kind, label }) => {
        const s = BASE[kind]
        return (
          <div key={kind} className="flex items-center gap-1.5">
            <div className={`size-2.5 rounded-sm border ${s.bg} ${s.border}`} />
            <span className="text-[10px] text-muted-foreground">{label}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────

function GraphEmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      <GitBranch className="size-8 text-muted-foreground/30" />
      <p className="text-sm font-medium">Loading graph…</p>
      <p className="text-xs text-muted-foreground max-w-xs">
        The agent graph appears here once connected. Nodes light up as spans fire during execution.
      </p>
    </div>
  )
}

// ── Canvas ─────────────────────────────────────────────────────────────────────

function GraphCanvas({ schema, highlights }: { schema: AgentSchema | null; highlights: NodeHighlights }) {
  const { nodes, edges } = useMemo(
    () => buildGraph(schema, highlights),
    [schema, highlights],
  )

  if (!schema) return <GraphEmptyState />

  return (
    <div className="relative h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
        className="bg-background"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="opacity-30" />
        <Controls className="!bg-card !border-border" />
        <MiniMap
          nodeColor={node => MINIMAP_COLORS[(node.data as { kind: NodeKind }).kind] ?? "#888"}
          className="!bg-card !border-border"
        />
      </ReactFlow>
      <Legend />
    </div>
  )
}

// ── Public export ──────────────────────────────────────────────────────────────

interface Props {
  schema: AgentSchema | null
  highlights: NodeHighlights
}

export function LiveGraph({ schema, highlights }: Props) {
  return (
    <div className="h-full">
      <ReactFlowProvider>
        <GraphCanvas schema={schema} highlights={highlights} />
      </ReactFlowProvider>
    </div>
  )
}
