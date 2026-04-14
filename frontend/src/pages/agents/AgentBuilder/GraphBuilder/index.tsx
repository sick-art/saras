/**
 * GraphBuilder — React Flow canvas visualising the agent's condition/goal graph.
 *
 * Node types:
 *   - agent-root: The top-level agent node (persona + model info)
 *   - condition: A Condition block (blue)
 *   - goal: A Goal block (green) — child of its condition
 *   - tool: A Tool node (amber) — referenced by goals
 *   - handoff: A Handoff node (purple)
 *   - interrupt: An Interrupt Trigger node (red)
 *
 * Edges:
 *   - root → condition (solid)
 *   - condition → goal (solid)
 *   - goal → tool (dashed, tool-use reference)
 *   - root → handoff (dashed)
 *   - root → interrupt (dashed)
 *
 * Layout: dagre-style auto layout using simple deterministic positioning.
 * (No dagre dependency needed — we compute positions manually from the schema structure.)
 *
 * Nodes are read-only in this view. Clicking a node shows its description.
 * The canvas is reactive to YAML changes via useAgentStore().parsedSchema.
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
import { useAgentStore } from "@/stores/agent.store"
import type { AgentSchema } from "@/types/agent"

// ── Node colors ────────────────────────────────────────────────────────────────

const NODE_STYLES = {
  root:      { bg: "bg-primary",    border: "border-primary",    text: "text-primary-foreground" },
  condition: { bg: "bg-blue-500/10", border: "border-blue-500/50", text: "text-blue-700 dark:text-blue-400" },
  goal:      { bg: "bg-emerald-500/10", border: "border-emerald-500/50", text: "text-emerald-700 dark:text-emerald-400" },
  tool:      { bg: "bg-amber-500/10", border: "border-amber-500/50", text: "text-amber-700 dark:text-amber-400" },
  handoff:   { bg: "bg-purple-500/10", border: "border-purple-500/50", text: "text-purple-700 dark:text-purple-400" },
  interrupt: { bg: "bg-red-500/10",  border: "border-red-500/50",  text: "text-red-700 dark:text-red-400" },
} as const

type NodeKind = keyof typeof NODE_STYLES

// ── Custom node component ──────────────────────────────────────────────────────

function AgentNode({ data }: NodeProps) {
  const { kind, label, description, icon: Icon } = data as {
    kind: NodeKind
    label: string
    description?: string
    icon: React.ComponentType<{ className?: string }>
  }
  const style = NODE_STYLES[kind]

  return (
    <div
      className={`rounded-lg border px-3 py-2 shadow-sm min-w-[140px] max-w-[200px] ${style.bg} ${style.border}`}
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

// ── Layout computation ─────────────────────────────────────────────────────────

const H_GAP = 220
const V_GAP = 120

function buildGraph(schema: AgentSchema | null): { nodes: Node[]; edges: Edge[] } {
  if (!schema) return { nodes: [], edges: [] }

  const nodes: Node[] = []
  const edges: Edge[] = []

  const addNode = (
    id: string,
    x: number,
    y: number,
    kind: NodeKind,
    label: string,
    description?: string,
    Icon: React.ComponentType<{ className?: string }> = Bot,
  ) => {
    nodes.push({
      id,
      type: "agent",
      position: { x, y },
      data: { kind, label, description, icon: Icon },
    })
  }

  const addEdge = (source: string, target: string, dashed = false) => {
    edges.push({
      id: `${source}-${target}`,
      source,
      target,
      animated: dashed,
      style: dashed ? { strokeDasharray: "4 2", stroke: "var(--border)" } : { stroke: "var(--border)" },
    })
  }

  // Root node
  addNode("root", 0, 0, "root", schema.name || "Agent", schema.persona?.slice(0, 60), Bot)

  // Conditions + goals
  const conditions = schema.conditions ?? []
  const totalConditionWidth = conditions.length * H_GAP
  const condStartX = -(totalConditionWidth / 2) + H_GAP / 2

  conditions.forEach((cond, ci) => {
    const condX = condStartX + ci * H_GAP
    const condId = `cond-${ci}`
    addNode(condId, condX, V_GAP, "condition", cond.name, cond.description, GitBranch)
    addEdge("root", condId)

    const goals = cond.goals ?? []
    const totalGoalWidth = goals.length * (H_GAP * 0.8)
    const goalStartX = condX - totalGoalWidth / 2 + (H_GAP * 0.8) / 2

    goals.forEach((goal, gi) => {
      const goalId = `goal-${ci}-${gi}`
      addNode(goalId, goalStartX + gi * (H_GAP * 0.8), V_GAP * 2, "goal", goal.name, goal.description, Target)
      addEdge(condId, goalId)
    })
  })

  // Tools
  const tools = schema.tools ?? []
  tools.forEach((tool, ti) => {
    const toolId = `tool-${ti}`
    const toolX = condStartX + ti * (H_GAP * 0.75) - H_GAP * 0.5
    addNode(toolId, toolX, V_GAP * 3, "tool", tool.name, `${tool.type}: ${tool.description?.slice(0, 40)}`, Wrench)

    // Find goals that reference this tool
    conditions.forEach((cond, ci) => {
      cond.goals?.forEach((goal, gi) => {
        if (goal.tools?.includes(tool.name)) {
          addEdge(`goal-${ci}-${gi}`, toolId, true)
        }
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

// ── Empty state ────────────────────────────────────────────────────────────────

function GraphEmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      <GitBranch className="size-8 text-muted-foreground/40" />
      <p className="text-sm font-medium">No agent loaded</p>
      <p className="text-xs text-muted-foreground max-w-xs">
        Build your agent in the Chat or Form tab to see the graph.
      </p>
    </div>
  )
}

// ── Canvas ─────────────────────────────────────────────────────────────────────

function GraphCanvas() {
  const { parsedSchema } = useAgentStore()
  const { nodes, edges } = useMemo(() => buildGraph(parsedSchema), [parsedSchema])

  if (!parsedSchema) return <GraphEmptyState />

  return (
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
      <Background
        variant={BackgroundVariant.Dots}
        gap={20}
        size={1}
        className="opacity-30"
      />
      <Controls className="!bg-card !border-border" />
      <MiniMap
        nodeColor={(node) => {
          const kind = (node.data as { kind: NodeKind }).kind
          const colors: Record<NodeKind, string> = {
            root: "hsl(var(--primary))",
            condition: "#3b82f6",
            goal: "#10b981",
            tool: "#f59e0b",
            handoff: "#a855f7",
            interrupt: "#ef4444",
          }
          return colors[kind] ?? "#888"
        }}
        className="!bg-card !border-border"
      />
    </ReactFlow>
  )
}

// ── Public export (wrapped in provider) ───────────────────────────────────────

export function GraphBuilder() {
  return (
    <div className="h-full">
      <ReactFlowProvider>
        <GraphCanvas />
      </ReactFlowProvider>
    </div>
  )
}
