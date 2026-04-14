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
 *   turn_cancelled    {}   — emitted when end_simulation aborts a running turn
 *   span              { span_type, data }
 *   error             { message }
 *   reset_ack         {}
 *   simulation_ended  {}   — ack for end_simulation; triggers auto-reconnect
 *
 * Span → node ID mapping lives in resolveHighlights() below.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { ChevronLeft, RotateCcw, Wifi, WifiOff, Loader2, Square, StopCircle, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable"
import { api } from "@/lib/api"
import type { AgentRecord, AgentSchema } from "@/types/agent"
import { ConversationPane } from "./ConversationPane"
import { LiveGraph } from "./LiveGraph"
import { SaveAsGoldenDialog } from "@/components/evals/SaveAsGoldenDialog"

// ── Public types (shared with child components) ────────────────────────────────

export type WsStatus = "connecting" | "connected" | "disconnected" | "error" | "ended"
export type TurnType = "response" | "slot_fill" | "interrupt" | "handoff"
export type SimMode = "standard" | "good" | "bad"

export interface SimMessage {
  id: string
  role: "user" | "agent" | "system" | "error"
  content: string
  turn_type?: TurnType
  tokens?: { input: number; output: number }
  cost_usd?: number
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
  const [simMode, setSimMode] = useState<SimMode>("standard")

  // Node highlights for LiveGraph
  const [highlights, setHighlights] = useState<NodeHighlights>(new Map())

  // Save as golden
  const [goldenOpen, setGoldenOpen] = useState(false)

  // Refs (stable across renders, not triggering re-connections)
  const wsRef = useRef<WebSocket | null>(null)
  const schemaRef = useRef<AgentSchema | null>(null)
  const lastDecisionRef = useRef<Record<string, unknown> | null>(null)
  const timerMapRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const connectedRef = useRef(false)
  const simModeRef = useRef<SimMode>("standard")
  const endedRef = useRef(false)
  // Stable ref to reconnect so the WS onmessage closure can call the latest version
  const reconnectRef = useRef<(() => void) | null>(null)

  // Keep refs in sync with state / callbacks
  useEffect(() => { schemaRef.current = schema }, [schema])
  useEffect(() => { simModeRef.current = simMode }, [simMode])

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

    const url = `${WS_BASE}/api/projects/${projectId}/agents/${agentId}/simulate?mode=${simMode}`
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
          if (tok) {
            setMessages(prev => {
              const idx = [...prev].reverse().findIndex(m => m.role === "agent")
              if (idx < 0) return prev
              const ri = prev.length - 1 - idx
              return prev.map((m, i) => i === ri ? { ...m, tokens: tok, cost_usd: cost } : m)
            })
          }
          break
        }

        case "span": {
          const pairs = resolveHighlights(msg.span_type as string, (msg.data ?? {}) as Record<string, unknown>)
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

        case "simulation_ended":
          // Force-reconnect to pick up any agent changes saved since last connect
          endedRef.current = true
          setIsThinking(false)
          reconnectRef.current?.()
          break

        case "turn_cancelled":
          setIsThinking(false)
          break

        case "reset_ack":
          setHighlights(new Map())
          lastDecisionRef.current = null
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
  }, [projectId, agentId, simMode, resolveHighlights, addHighlight])

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

    const currentMode = simModeRef.current
    const url = `${WS_BASE}/api/projects/${projectId}/agents/${agentId}/simulate?mode=${currentMode}`
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
          if (tok) {
            setMessages(p => {
              const idx = [...p].reverse().findIndex(m => m.role === "agent")
              if (idx < 0) return p
              const ri = p.length - 1 - idx
              return p.map((m, i) => i === ri ? { ...m, tokens: tok, cost_usd: cost } : m)
            })
          }
          break
        }
        case "span": {
          const pairs = resolveHighlights(msg.span_type as string, (msg.data ?? {}) as Record<string, unknown>)
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
        case "simulation_ended":
          endedRef.current = true
          setIsThinking(false)
          reconnectRef.current?.()
          break
        case "turn_cancelled":
          setIsThinking(false)
          break
        case "reset_ack":
          setHighlights(new Map())
          lastDecisionRef.current = null
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

  // Keep reconnectRef always pointing at the latest reconnect so WS message
  // handlers (closures) can call it without stale-closure issues.
  useEffect(() => { reconnectRef.current = reconnect }, [reconnect])

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
      ws.send(JSON.stringify({ type: "end_session" }))
    } else {
      // Already disconnected — just mark as ended locally
      setWsStatus("ended")
      setIsThinking(false)
      setMessages(prev => [...prev, { id: uid(), role: "system", content: "Session ended." }])
    }
  }, [])

  const endSimulation = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Ask the backend to cancel any in-flight turn and close; the server
      // replies with simulation_ended which triggers an auto-reconnect,
      // picking up any agent changes saved since this session started.
      ws.send(JSON.stringify({ type: "end_simulation" }))
    } else {
      // Already disconnected — just reconnect fresh
      reconnectRef.current?.()
    }
  }, [])

  const changeMode = useCallback((mode: SimMode) => {
    // Update mode — the useEffect (which depends on simMode) will handle
    // closing the old WS and opening a new one with the new mode.
    // Reset conversation state so the new session starts clean.
    setSimMode(mode)
    setMessages([])
    setIsThinking(false)
    setHighlights(new Map())
    lastDecisionRef.current = null
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
          {/* Simulation mode selector — always visible */}
          <SimModeSelector mode={simMode} onChange={changeMode} disabled={wsStatus === "connecting"} />

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

          {/* End Simulation — stops any running turn, reconnects fresh to pick up agent changes */}
          <Button
            size="sm"
            variant="destructive"
            onClick={endSimulation}
            disabled={wsStatus === "connecting"}
          >
            <StopCircle data-icon="inline-start" />
            End Simulation
          </Button>

          {/* End — only visible when connected */}
          {wsStatus === "connected" && (
            <Button
              size="sm"
              variant="destructive"
              onClick={endSession}
            >
              <Square data-icon="inline-start" />
              End
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
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize="55%" minSize="30%">
          <LiveGraph schema={schema} highlights={highlights} />
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

// ── Sim mode selector ──────────────────────────────────────────────────────────

const MODE_CONFIG: Record<SimMode, { label: string; className: string }> = {
  standard: { label: "Standard", className: "text-muted-foreground" },
  good:     { label: "Perfect",  className: "text-emerald-600" },
  bad:      { label: "Flawed",   className: "text-amber-600" },
}

function SimModeSelector({
  mode,
  onChange,
  disabled,
}: {
  mode: SimMode
  onChange: (m: SimMode) => void
  disabled: boolean
}) {
  return (
    <div className="flex items-center rounded-md border border-border overflow-hidden text-[11px] font-medium shrink-0">
      {(["good", "standard", "bad"] as SimMode[]).map((m) => {
        const { label, className } = MODE_CONFIG[m]
        const active = mode === m
        return (
          <button
            key={m}
            disabled={disabled}
            onClick={() => onChange(m)}
            className={[
              "px-2.5 py-1 transition-colors",
              active
                ? `bg-muted ${className}`
                : "text-muted-foreground hover:bg-muted/50",
              disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
            ].join(" ")}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
