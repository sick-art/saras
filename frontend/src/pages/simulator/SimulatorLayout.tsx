/**
 * SimulatorLayout — full-screen simulator for testing agent conversations.
 *
 * Route: /projects/:projectId/agents/:agentId/simulate
 * Outside AppShell — full-screen like BuilderLayout.
 *
 * Owns the WebSocket connection and distributes state:
 *   - Turn messages + status  → ConversationPane
 *   - Span-driven highlights  → LiveGraph
 *
 * WS message protocol (server → client):
 *   connected         { session_id, agent_name, agent_version }
 *   turn_start        {}
 *   agent_message     { content, turn_type, router_decision }
 *   turn_end          { tokens: { input, output }, cost_usd, run_id }
 *   turn_cancelled    {}   — emitted when end_session aborts a running turn
 *   span              { span_type, data }
 *   error             { message }
 *   reset_ack         {}
 *   session_ended     {}   — ack for end_session; backend has cancelled any
 *                            in-flight turn and marked its Run row 'cancelled'
 *
 * Span → node ID mapping lives in resolveHighlights() below.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { ChevronLeft, RotateCcw, Wifi, WifiOff, Loader2, Square, BookOpen, Bug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable"
import { api } from "@/lib/api"
import type { AgentRecord, AgentSchema } from "@/types/agent"
import type { Span, SpanType } from "@/types/trace"
import { ConversationPane } from "./ConversationPane"
import { LiveGraph } from "./LiveGraph"
import { SaveAsGoldenDialog } from "@/components/evals/SaveAsGoldenDialog"

// ── Public types (shared with child components) ────────────────────────────────

export type WsStatus = "connecting" | "connected" | "disconnected" | "error" | "ended"
export type TurnType = "response" | "slot_fill" | "interrupt" | "handoff"

export interface SimMessage {
  id: string
  role: "user" | "agent" | "system" | "error"
  content: string
  turn_type?: TurnType
  tokens?: { input: number; output: number }
  cost_usd?: number
  spanIds?: string[]
}

const DEBUG_VIEW_KEY = "saras.debugView"

function spanFromEvent(event: Record<string, unknown>): Span | null {
  const data = (event.data ?? {}) as Record<string, unknown>
  const id = data.span_id as string | undefined
  const runId = data.run_id as string | undefined
  const spanType = event.span_type as string | undefined
  const timestamp = event.timestamp as string | undefined
  if (!id || !spanType || !timestamp) return null
  // Strip wrapper fields from payload; keep everything else for SpanDetailPanel
  const { span_id: _span_id, run_id: _run_id, ...payload } = data
  void _span_id; void _run_id
  return {
    id,
    run_id: runId ?? "",
    parent_span_id: null,
    name: spanType,
    type: spanType as SpanType,
    started_at: timestamp,
    ended_at: null,
    duration_ms: (payload.duration_ms as number | undefined) ?? null,
    payload: payload as Span["payload"],
  }
}

/** nodeId → highlight kind (expires after timeout set in addHighlight) */
export type NodeHighlights = Map<string, "pulse" | "active">

// ── Constants ──────────────────────────────────────────────────────────────────

const WS_BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/^http/, "ws")
let _id = 0
const uid = () => String(++_id)

function snakeName(name: string): string {
  return name.toLowerCase().replace(/[\s-]+/g, "_")
}

// ── SimulatorLayout ────────────────────────────────────────────────────────────

export function SimulatorLayout() {
  const { projectId = "", agentId = "" } = useParams<{ projectId: string; agentId: string }>()

  // Agent info
  const [agentName, setAgentName] = useState("")
  const [schema, setSchema] = useState<AgentSchema | null>(null)

  // WS state
  const [wsStatus, setWsStatus] = useState<WsStatus>("disconnected")
  const [messages, setMessages] = useState<SimMessage[]>([])
  const [isThinking, setIsThinking] = useState(false)

  // Debug view (persisted across sessions via localStorage)
  const [debugView, setDebugView] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem(DEBUG_VIEW_KEY) === "1"
  })
  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem(DEBUG_VIEW_KEY, debugView ? "1" : "0")
  }, [debugView])

  // Span capture: every span emitted this session, keyed by span id.
  const [spansById, setSpansById] = useState<Map<string, Span>>(new Map())

  // Node highlights for LiveGraph
  const [highlights, setHighlights] = useState<NodeHighlights>(new Map())

  // Progressive disclosure: nodes that have been activated (persist until reset)
  const [activatedNodes, setActivatedNodes] = useState<Set<string>>(new Set())

  // Save as golden
  const [goldenOpen, setGoldenOpen] = useState(false)

  // Refs (stable across renders, not triggering re-connections)
  const wsRef = useRef<WebSocket | null>(null)
  const schemaRef = useRef<AgentSchema | null>(null)
  const lastDecisionRef = useRef<Record<string, unknown> | null>(null)
  const timerMapRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const connectedRef = useRef(false)
  const endedRef = useRef(false)
  // Span IDs that have arrived for the in-flight turn; drained into the last
  // agent message on turn_end so pills attach to the correct turn.
  const pendingSpanIdsRef = useRef<string[]>([])

  // Keep refs in sync with state / callbacks
  useEffect(() => { schemaRef.current = schema }, [schema])

  // ── Load schema from API ───────────────────────────────────────────────────

  useEffect(() => {
    if (!projectId || !agentId) return
    api.get<AgentRecord>(`/projects/${projectId}/agents/${agentId}`)
      .then(async (record) => {
        setAgentName(record.name)
        const { load } = await import("js-yaml")
        const raw = load(record.yaml_content) as Record<string, unknown>
        const parsed = (raw?.agent ?? null) as AgentSchema | null
        setSchema(parsed)
        schemaRef.current = parsed
      })
      .catch(() => {})
  }, [projectId, agentId])

  // ── Highlight helpers ──────────────────────────────────────────────────────

  const addHighlight = useCallback((nodeId: string, kind: "pulse" | "active", ms = 2000) => {
    setHighlights(prev => { const m = new Map(prev); m.set(nodeId, kind); return m })
    // Track activated nodes for progressive disclosure (tools, handoffs, interrupts)
    if (nodeId.startsWith("tool-") || nodeId.startsWith("handoff-") || nodeId.startsWith("interrupt-")) {
      setActivatedNodes(prev => { if (prev.has(nodeId)) return prev; const s = new Set(prev); s.add(nodeId); return s })
    }
    const existing = timerMapRef.current.get(nodeId)
    if (existing) clearTimeout(existing)
    const t = setTimeout(() => {
      setHighlights(prev => { const m = new Map(prev); m.delete(nodeId); return m })
      timerMapRef.current.delete(nodeId)
    }, ms)
    timerMapRef.current.set(nodeId, t)
  }, [])

  // Resolve span events → list of [nodeId, kind] pairs using current schema
  const resolveHighlights = useCallback((spanType: string, data: Record<string, unknown>): [string, "pulse" | "active"][] => {
    const s = schemaRef.current
    if (!s) return []

    const conditions = s.conditions ?? []
    const tools      = s.tools ?? []
    const interrupts = s.interrupt_triggers ?? []
    const handoffs   = s.handoffs ?? []

    const findCond   = (name: string) => conditions.findIndex(c => c.name === name)
    const findGoal   = (ci: number, name: string) => (conditions[ci]?.goals ?? []).findIndex(g => g.name === name)
    const findTool   = (snake: string) => tools.findIndex(t => snakeName(t.name) === snake)
    const findInter  = (name: string) => interrupts.findIndex(t => t.name === name)
    const findHandoff = (name: string) => handoffs.findIndex(h => h.name === name)

    switch (spanType) {
      case "router_decision": {
        const dec = (data.decision ?? {}) as Record<string, unknown>
        lastDecisionRef.current = dec
        const pairs: [string, "pulse" | "active"][] = [["root", "pulse"]]
        const condName = dec.active_condition as string | null
        if (condName) {
          const ci = findCond(condName)
          if (ci >= 0) pairs.push([`cond-${ci}`, "active"])
          const goalName = dec.active_goal as string | null
          if (goalName) {
            const gi = findGoal(ci, goalName)
            if (gi >= 0) pairs.push([`goal-${ci}-${gi}`, "active"])
          }
        }
        return pairs
      }
      case "llm_call_start":
      case "llm_call_end":
        return [["root", "pulse"]]
      case "tool_call": {
        const ti = findTool(data.tool as string)
        return ti >= 0 ? [[`tool-${ti}`, "active"]] : []
      }
      case "slot_fill": {
        const dec = lastDecisionRef.current
        if (!dec) return []
        const ci = findCond(dec.active_condition as string)
        if (ci < 0) return []
        const gi = findGoal(ci, dec.active_goal as string)
        return gi >= 0 ? [[`goal-${ci}-${gi}`, "active"]] : []
      }
      case "interrupt_triggered": {
        const idx = findInter(data.trigger as string)
        return idx >= 0 ? [[`interrupt-${idx}`, "active"]] : []
      }
      case "handoff_triggered": {
        const idx = findHandoff(data.handoff as string)
        return idx >= 0 ? [[`handoff-${idx}`, "active"]] : []
      }
      default:
        return []
    }
  }, []) // stable — reads via refs

  // ── WebSocket lifecycle ────────────────────────────────────────────────────

  useEffect(() => {
    if (!projectId || !agentId) return

    // Per-effect flag: prevents stale onclose/onerror from this WS
    // overriding state set by a newer effect after mode change / reconnect.
    let active = true

    connectedRef.current = false
    endedRef.current = false

    const url = `${WS_BASE}/api/projects/${projectId}/agents/${agentId}/simulate`
    setWsStatus("connecting")
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onmessage = (ev) => {
      if (!active) return
      let msg: Record<string, unknown>
      try { msg = JSON.parse(ev.data) } catch { return }
      const type = msg.type as string

      switch (type) {
        case "connected":
          connectedRef.current = true
          setWsStatus("connected")
          if (msg.agent_name) setAgentName(n => n || (msg.agent_name as string))
          setMessages([{
            id: uid(), role: "system",
            content: `Connected to ${msg.agent_name ?? "agent"} · v${msg.agent_version ?? "1"}`,
          }])
          break

        case "turn_start":
          setIsThinking(true)
          break

        case "agent_message":
          setIsThinking(false)
          setMessages(prev => [...prev, {
            id: uid(),
            role: "agent",
            content: msg.content as string,
            turn_type: msg.turn_type as TurnType,
          }])
          break

        case "turn_end": {
          const tok = msg.tokens as { input: number; output: number } | undefined
          const cost = msg.cost_usd as number | undefined
          const pendingIds = [...pendingSpanIdsRef.current]
          pendingSpanIdsRef.current = []
          setMessages(prev => {
            const idx = [...prev].reverse().findIndex(m => m.role === "agent")
            if (idx < 0) return prev
            const ri = prev.length - 1 - idx
            return prev.map((m, i) => i === ri
              ? {
                  ...m,
                  ...(tok ? { tokens: tok, cost_usd: cost } : {}),
                  spanIds: [...(m.spanIds ?? []), ...pendingIds],
                }
              : m)
          })
          break
        }

        case "span": {
          const spanType = msg.span_type as string
          const data = (msg.data ?? {}) as Record<string, unknown>
          const span = spanFromEvent(msg)
          if (span) {
            pendingSpanIdsRef.current.push(span.id)
            setSpansById(prev => {
              const next = new Map(prev)
              next.set(span.id, span)
              return next
            })
          }
          const pairs = resolveHighlights(spanType, data)
          pairs.forEach(([id, kind]) => addHighlight(id, kind))
          break
        }

        case "error":
          setIsThinking(false)
          setMessages(prev => [...prev, { id: uid(), role: "error", content: msg.message as string }])
          break

        case "session_ended":
          endedRef.current = true
          setWsStatus("ended")
          setIsThinking(false)
          setMessages(prev => [...prev, { id: uid(), role: "system", content: "Session ended." }])
          break

        case "turn_cancelled":
          setIsThinking(false)
          break

        case "reset_ack":
          setHighlights(new Map())
          setActivatedNodes(new Set())
          lastDecisionRef.current = null
          pendingSpanIdsRef.current = []
          setSpansById(new Map())
          setMessages([{ id: uid(), role: "system", content: "Conversation reset." }])
          break
      }
    }

    ws.onclose = () => {
      if (!active) return   // stale — a newer effect already owns the state
      setIsThinking(false)
      wsRef.current = null
      if (!endedRef.current) {
        setWsStatus(connectedRef.current ? "disconnected" : "error")
      }
    }

    ws.onerror = () => {
      if (!active) return
      setWsStatus("error")
      setIsThinking(false)
    }

    return () => {
      active = false        // disable stale callbacks before cleanup
      ws.close()
      timerMapRef.current.forEach(t => clearTimeout(t))
    }
  }, [projectId, agentId, resolveHighlights, addHighlight])

  // ── Reconnect ──────────────────────────────────────────────────────────────

  const reconnect = useCallback(() => {
    if (!projectId || !agentId) return

    // Tear down the current WS (if any) before opening a new one.
    // We don't rely on the useEffect here since reconnect can be called
    // independently of a simMode change.
    const prev = wsRef.current
    if (prev) {
      prev.onclose = null  // prevent stale onclose from firing
      prev.onerror = null
      prev.close()
    }

    connectedRef.current = false
    endedRef.current = false
    setWsStatus("connecting")
    setMessages([])
    setIsThinking(false)
    setHighlights(new Map())
    setSpansById(new Map())
    pendingSpanIdsRef.current = []

    const url = `${WS_BASE}/api/projects/${projectId}/agents/${agentId}/simulate`
    const ws = new WebSocket(url)
    wsRef.current = ws

    const handleMsg = (ev: MessageEvent) => {
      let msg: Record<string, unknown>
      try { msg = JSON.parse(ev.data) } catch { return }
      const type = msg.type as string
      switch (type) {
        case "connected":
          connectedRef.current = true
          setWsStatus("connected")
          if (msg.agent_name) setAgentName(n => n || (msg.agent_name as string))
          setMessages([{ id: uid(), role: "system", content: `Connected to ${msg.agent_name ?? "agent"} · v${msg.agent_version ?? "1"}` }])
          break
        case "turn_start": setIsThinking(true); break
        case "agent_message":
          setIsThinking(false)
          setMessages(p => [...p, { id: uid(), role: "agent", content: msg.content as string, turn_type: msg.turn_type as TurnType }])
          break
        case "turn_end": {
          const tok = msg.tokens as { input: number; output: number } | undefined
          const cost = msg.cost_usd as number | undefined
          const pendingIds = [...pendingSpanIdsRef.current]
          pendingSpanIdsRef.current = []
          setMessages(p => {
            const idx = [...p].reverse().findIndex(m => m.role === "agent")
            if (idx < 0) return p
            const ri = p.length - 1 - idx
            return p.map((m, i) => i === ri
              ? {
                  ...m,
                  ...(tok ? { tokens: tok, cost_usd: cost } : {}),
                  spanIds: [...(m.spanIds ?? []), ...pendingIds],
                }
              : m)
          })
          break
        }
        case "span": {
          const spanType = msg.span_type as string
          const data = (msg.data ?? {}) as Record<string, unknown>
          const span = spanFromEvent(msg)
          if (span) {
            pendingSpanIdsRef.current.push(span.id)
            setSpansById(prev => {
              const next = new Map(prev)
              next.set(span.id, span)
              return next
            })
          }
          const pairs = resolveHighlights(spanType, data)
          pairs.forEach(([id, kind]) => addHighlight(id, kind))
          break
        }
        case "error":
          setIsThinking(false)
          setMessages(p => [...p, { id: uid(), role: "error", content: msg.message as string }])
          break
        case "session_ended":
          endedRef.current = true
          setWsStatus("ended")
          setIsThinking(false)
          setMessages(p => [...p, { id: uid(), role: "system", content: "Session ended." }])
          break
        case "turn_cancelled":
          setIsThinking(false)
          break
        case "reset_ack":
          setHighlights(new Map())
          setActivatedNodes(new Set())
          lastDecisionRef.current = null
          pendingSpanIdsRef.current = []
          setSpansById(new Map())
          setMessages([{ id: uid(), role: "system", content: "Conversation reset." }])
          break
      }
    }

    ws.onmessage = handleMsg
    ws.onclose = () => {
      if (wsRef.current !== ws) return  // stale — reconnect was called again
      setIsThinking(false)
      wsRef.current = null
      if (!endedRef.current) {
        setWsStatus(connectedRef.current ? "disconnected" : "error")
      }
    }
    ws.onerror = () => {
      if (wsRef.current !== ws) return
      setWsStatus("error")
      setIsThinking(false)
    }
  }, [projectId, agentId, resolveHighlights, addHighlight])


  // ── Send helpers ───────────────────────────────────────────────────────────

  const sendMessage = useCallback((content: string) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    setMessages(prev => [...prev, { id: uid(), role: "user", content }])
    ws.send(JSON.stringify({ type: "user_message", content }))
  }, [])

  const sendReset = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: "reset" }))
  }, [])

  const endSession = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Backend cancels any in-flight turn (run_turn's CancelledError handler
      // marks the Run row 'cancelled' and syncs DuckDB), then replies with
      // session_ended which closes the WS.
      ws.send(JSON.stringify({ type: "end_session" }))
    } else {
      // Already disconnected — mark as ended locally.
      setWsStatus("ended")
      setIsThinking(false)
      setMessages(prev => [...prev, { id: uid(), role: "system", content: "Session ended." }])
    }
  }, [])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex items-center justify-between gap-4 border-b border-border px-4 py-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Button
            variant="ghost"
            size="icon"
            className="size-7 shrink-0"
            render={<Link to={`/projects/${projectId}/agents/${agentId}/builder`} />}
          >
            <ChevronLeft />
          </Button>
          <span className="font-medium text-sm truncate">{agentName || "Simulator"}</span>
          <WsStatusBadge status={wsStatus} />
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Debug view toggle — surfaces internal spans as clickable pills below each assistant turn. */}
          <DebugViewToggle enabled={debugView} onChange={setDebugView} />

          {/* Reconnect / New Session — shown when not live */}
          {(wsStatus === "disconnected" || wsStatus === "error" || wsStatus === "ended") && (
            <Button size="sm" variant="outline" onClick={reconnect}>
              {wsStatus === "ended" ? "New Session" : "Reconnect"}
            </Button>
          )}

          {/* Save as Golden — only when there are turns to save */}
          {messages.some(m => m.role === "user") && (
            <Button size="sm" variant="outline" onClick={() => setGoldenOpen(true)}>
              <BookOpen data-icon="inline-start" />
              Save as Golden
            </Button>
          )}

          {/* Reset — always visible, disabled when not connected (matches original behaviour) */}
          <Button
            size="sm"
            variant="outline"
            onClick={sendReset}
            disabled={wsStatus !== "connected"}
          >
            <RotateCcw data-icon="inline-start" />
            Reset
          </Button>

          {/* End session — cancels any in-flight turn server-side and closes the WS */}
          {wsStatus === "connected" && (
            <Button
              size="sm"
              variant="destructive"
              onClick={endSession}
            >
              <Square data-icon="inline-start" />
              End session
            </Button>
          )}
        </div>
      </header>

      {/* Save as Golden dialog */}
      {goldenOpen && (
        <SaveAsGoldenDialog
          open={goldenOpen}
          onClose={() => setGoldenOpen(false)}
          source={{
            kind: "simulation",
            history: messages
              .filter(m => m.role === "user" || m.role === "agent")
              .map(m => ({ role: m.role === "agent" ? "assistant" : "user", content: m.content })),
            agentId,
          }}
        />
      )}

      {/* Split pane */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1 overflow-hidden">
        <ResizablePanel defaultSize="45%" minSize="25%">
          <ConversationPane
            messages={messages}
            isThinking={isThinking}
            wsStatus={wsStatus}
            onSend={sendMessage}
            debugView={debugView}
            spansById={spansById}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize="55%" minSize="30%">
          <LiveGraph schema={schema} highlights={highlights} activatedNodes={activatedNodes} />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

// ── WS status badge ────────────────────────────────────────────────────────────

function WsStatusBadge({ status }: { status: WsStatus }) {
  if (status === "connected") {
    return (
      <Badge variant="outline" className="gap-1 text-emerald-600 border-emerald-500/40 text-[10px]">
        <Wifi className="size-2.5" />
        Live
      </Badge>
    )
  }
  if (status === "connecting") {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground text-[10px]">
        <Loader2 className="size-2.5 animate-spin" />
        Connecting
      </Badge>
    )
  }
  if (status === "ended") {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground border-muted text-[10px]">
        <Square className="size-2.5" />
        Ended
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-destructive border-destructive/40 text-[10px]">
      <WifiOff className="size-2.5" />
      {status === "error" ? "Error" : "Disconnected"}
    </Badge>
  )
}

// ── Debug view toggle ─────────────────────────────────────────────────────────

function DebugViewToggle({
  enabled,
  onChange,
}: {
  enabled: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={() => onChange(!enabled)}
      aria-pressed={enabled}
      className={enabled ? "bg-muted text-foreground" : "text-muted-foreground"}
      title={enabled ? "Hide internal span pills" : "Show internal span pills under each turn"}
    >
      <Bug data-icon="inline-start" />
      Debug view
    </Button>
  )
}
