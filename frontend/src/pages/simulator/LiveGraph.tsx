/**
 * LiveGraph — right panel of SimulatorLayout.
 *
 * React Flow canvas mirroring the compiled agent's condition/goal graph.
 * Nodes pulse and highlight in real time as WebSocket span events arrive.
 *
 * Uses dagre for automatic layout instead of manual positioning.
 * Implements progressive disclosure:
 *   Always visible: root, conditions, goals, sequences
 *   Shown when activated (stays visible): tools, handoffs, interrupts
 *
 * Span → node ID mapping (resolved upstream in SimulatorLayout):
 *   router_decision    → root pulse + active condition + active goal
 *   llm_call_start/end → root pulse
 *   tool_call          → tool node active
 *   slot_fill          → goal node active (from last router decision)
 *   interrupt_triggered → interrupt node active
 *   handoff_triggered  → handoff node active
 *
 * Node IDs are deterministic:
 *   root, cond-{i}, goal-{i}-{j}, seq-{i}-{j}-{s}, tool-{i}, handoff-{i}, interrupt-{i}
 */

import type { AgentSchema } from "@/types/agent"
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import dagre from "@dagrejs/dagre"
import { ArrowRightLeft, Bot, GitBranch, List, Target, Wrench, Zap } from "lucide-react"
import { useMemo } from "react"
import type { NodeHighlights } from "./SimulatorLayout"

// ── Node styles ────────────────────────────────────────────────────────────────

const BASE = {
  root:      { bg: "bg-primary/10",       border: "border-primary/40",      text: "text-primary" },
  condition: { bg: "bg-blue-500/10",      border: "border-blue-500/40",     text: "text-blue-700 dark:text-blue-400" },
  goal:      { bg: "bg-emerald-500/10",   border: "border-emerald-500/40",  text: "text-emerald-700 dark:text-emerald-400" },
  sequence:  { bg: "bg-sky-500/10",       border: "border-sky-500/40",      text: "text-sky-700 dark:text-sky-400" },
  tool:      { bg: "bg-amber-500/10",     border: "border-amber-500/40",    text: "text-amber-700 dark:text-amber-400" },
  handoff:   { bg: "bg-purple-500/10",    border: "border-purple-500/40",   text: "text-purple-700 dark:text-purple-400" },
  interrupt: { bg: "bg-red-500/10",       border: "border-red-500/40",      text: "text-red-700 dark:text-red-400" },
} as const

const ACTIVE = {
  root:      { bg: "bg-primary",          border: "border-primary",         text: "text-primary-foreground" },
  condition: { bg: "bg-blue-500/25",      border: "border-blue-500",        text: "text-blue-800 dark:text-blue-300" },
  goal:      { bg: "bg-emerald-500/25",   border: "border-emerald-500",     text: "text-emerald-800 dark:text-emerald-300" },
  sequence:  { bg: "bg-sky-500/25",       border: "border-sky-500",         text: "text-sky-800 dark:text-sky-300" },
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

// ── Dagre auto-layout ─────────────────────────────────────────────────────────

const DAGRE_CONFIG = {
  rankdir: "TB" as const,
  nodesep: 60,
  ranksep: 80,
  marginx: 20,
  marginy: 20,
}

function layoutWithDagre(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes

  const g = new dagre.graphlib.Graph()
  g.setGraph(DAGRE_CONFIG)
  g.setDefaultEdgeLabel(() => ({}))

  for (const node of nodes) {
    g.setNode(node.id, { width: 180, height: 60 })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  return nodes.map(node => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: { x: pos.x - 90, y: pos.y - 30 },
    }
  })
}

// ── Graph builder (progressive disclosure) ────────────────────────────────────

function buildGraph(
  schema: AgentSchema | null,
  highlights: NodeHighlights,
  activatedNodes: Set<string>,
): { nodes: Node[]; edges: Edge[] } {
  if (!schema) return { nodes: [], edges: [] }

  const nodes: Node[] = []
  const edges: Edge[] = []

  const addNode = (
    id: string,
    kind: NodeKind, label: string, description?: string,
    Icon: React.ComponentType<{ className?: string }> = Bot,
  ) => {
    nodes.push({
      id, type: "agent", position: { x: 0, y: 0 },
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
  addNode("root", "root", schema.name || "Agent", schema.persona?.slice(0, 60), Bot)

  // Conditions + goals + sequences
  const conditions = schema.conditions ?? []
  conditions.forEach((cond, ci) => {
    const condId = `cond-${ci}`
    addNode(condId, "condition", cond.name, cond.description, GitBranch)
    addEdge("root", condId)

    const goals = cond.goals ?? []
    goals.forEach((goal, gi) => {
      const goalId = `goal-${ci}-${gi}`
      addNode(goalId, "goal", goal.name, goal.description, Target)
      addEdge(condId, goalId)

      // Sequences under goals
      const sequences = goal.sequences ?? []
      sequences.forEach((seq, si) => {
        const seqId = `seq-${ci}-${gi}-${si}`
        addNode(seqId, "sequence", seq.name, seq.description, List)
        addEdge(goalId, seqId)
      })
    })
  })

  // Tools — only show if activated
  const tools = schema.tools ?? []
  tools.forEach((tool, ti) => {
    const toolId = `tool-${ti}`
    if (!activatedNodes.has(toolId)) return
    addNode(toolId, "tool", tool.name, `${tool.type}: ${tool.description?.slice(0, 40)}`, Wrench)
    conditions.forEach((cond, ci) => {
      cond.goals?.forEach((goal, gi) => {
        if (goal.tools?.includes(tool.name)) addEdge(`goal-${ci}-${gi}`, toolId, true)
      })
    })
  })

  // Handoffs — only show if activated
  const handoffs = schema.handoffs ?? []
  handoffs.forEach((h, hi) => {
    const hId = `handoff-${hi}`
    if (!activatedNodes.has(hId)) return
    addNode(hId, "handoff", h.name, `→ ${h.target}`, ArrowRightLeft)
    addEdge("root", hId, true)
  })

  // Interrupt triggers — only show if activated
  const interrupts = schema.interrupt_triggers ?? []
  interrupts.forEach((t, ti) => {
    const iId = `interrupt-${ti}`
    if (!activatedNodes.has(iId)) return
    addNode(iId, "interrupt", t.name, t.description, Zap)
    addEdge("root", iId, true)
  })

  // Apply dagre layout
  const laidOutNodes = layoutWithDagre(nodes, edges)

  return { nodes: laidOutNodes, edges }
}

// ── MiniMap color helper ───────────────────────────────────────────────────────

const MINIMAP_COLORS: Record<NodeKind, string> = {
  root:      "hsl(var(--primary))",
  condition: "#3b82f6",
  goal:      "#10b981",
  sequence:  "#0ea5e9",
  tool:      "#f59e0b",
  handoff:   "#a855f7",
  interrupt: "#ef4444",
}

// ── Legend ─────────────────────────────────────────────────────────────────────

const LEGEND_ITEMS: Array<{ kind: NodeKind; label: string }> = [
  { kind: "root",      label: "Agent" },
  { kind: "condition", label: "Condition" },
  { kind: "goal",      label: "Goal" },
  { kind: "sequence",  label: "Sequence" },
  { kind: "tool",      label: "Tool" },
  { kind: "handoff",   label: "Handoff" },
  { kind: "interrupt", label: "Interrupt" },
]

function Legend() {
  return (
    <div className="absolute bottom-2 left-15 z-10 flex flex-col gap-1 rounded-lg border border-border bg-card/90 px-2.5 py-2 backdrop-blur-sm">
      {LEGEND_ITEMS.map(({ kind, label }) => {
        const s = BASE[kind]
        return (
          <div key={kind} className="flex items-center gap-1.5">
            <div className={`size-2.5 rounded-sm border ${s.bg} ${s.border}`} />
            <span className="text-[10px] text-muted-foreground">{label}</span>
            {(kind === "tool" || kind === "handoff" || kind === "interrupt") && (
              <span className="text-[9px] text-muted-foreground/50">on activate</span>
            )}
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

function GraphCanvas({
  schema,
  highlights,
  activatedNodes,
}: {
  schema: AgentSchema | null
  highlights: NodeHighlights
  activatedNodes: Set<string>
}) {
  const { nodes, edges } = useMemo(
    () => buildGraph(schema, highlights, activatedNodes),
    [schema, highlights, activatedNodes],
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
  activatedNodes: Set<string>
}

export function LiveGraph({ schema, highlights, activatedNodes }: Props) {
  return (
    <div className="h-full">
      <ReactFlowProvider>
        <GraphCanvas schema={schema} highlights={highlights} activatedNodes={activatedNodes} />
      </ReactFlowProvider>
    </div>
  )
}
