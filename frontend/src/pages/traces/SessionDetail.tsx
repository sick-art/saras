/**
 * SessionDetail — multi-turn conversation session viewer.
 *
 * Route: /projects/:projectId/traces/sessions/:sessionId
 *
 * Three tabs:
 *   Chat     (default) — reconstructed conversation as message bubbles
 *   Traces              — per-run span waterfalls stacked vertically
 *   Timeline            — Gantt chart of all spans on a shared time axis
 */

import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  AlertCircle,
  BookOpen,
  Bot,
  Bug,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coins,
  ExternalLink,
  Hash,
  Layers,
  User,
  Wrench,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { SaveAsGoldenDialog } from "@/components/evals/SaveAsGoldenDialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  buildDepthMap,
  fmt_cost,
  fmt_ms,
  SPAN_CONFIG,
  DEFAULT_SPAN_CONFIG,
  SpanRow,
  ToolChips,
  toolCountsFromSpans,
} from "@/components/traces/SpanWaterfall"
import { TurnSpanPills } from "@/components/traces/TurnSpanPills"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { RunDetail, RunStatus, Span, SessionDetail as SessionDetailType, LLMMessage } from "@/types/trace"

const DEBUG_VIEW_KEY = "saras.debugView"

function useDebugView(): [boolean, (value: boolean) => void] {
  const [enabled, setEnabled] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem(DEBUG_VIEW_KEY) === "1"
  })
  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem(DEBUG_VIEW_KEY, enabled ? "1" : "0")
  }, [enabled])
  return [enabled, setEnabled]
}

// ── Local helpers ──────────────────────────────────────────────────────────────

function fmtDur(started: string, ended: string | null): string {
  if (!ended) return "—"
  const ms = new Date(ended).getTime() - new Date(started).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function fmtRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000)     return "just now"
  if (ms < 3_600_000)  return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`
  return new Date(iso).toLocaleDateString()
}

// ── Status badge ───────────────────────────────────────────────────────────────

const STATUS_DOT_CLASS: Record<RunStatus, string> = {
  running:   "bg-blue-500 animate-pulse",
  completed: "bg-emerald-500",
  failed:    "bg-red-500",
  cancelled: "bg-muted-foreground",
}

function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium capitalize text-muted-foreground">
      <span className={cn("size-1.5 rounded-full shrink-0", STATUS_DOT_CLASS[status] ?? "bg-muted")} />
      {status}
    </span>
  )
}

// ── Conversation reconstruction ────────────────────────────────────────────────

interface ConversationTurn {
  runId: string
  runIndex: number
  userMessage: string | null
  toolCalls: Array<{ tool: string; arguments: Record<string, unknown> | null; result: string | null }>
  assistantMessage: string | null
  turnType: string | null
  inputTokens: number
  outputTokens: number
  costUsd: number
}

function extractTurns(runs: RunDetail[]): ConversationTurn[] {
  const turns: ConversationTurn[] = []

  for (let i = 0; i < runs.length; i++) {
    const run = runs[i]
    const spans = [...run.spans].sort(
      (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
    )

    // Prefer the authoritative per-turn span fields:
    //   router_decision.payload.user_message  — raw user input for this turn
    //   turn_complete.payload.content         — final assistant output (all turn types)
    //   turn_complete.payload.turn_type       — response | slot_fill | interrupt | handoff
    // Fall back to reconstruction from llm_call_* spans for older runs that
    // predate those fields being added.
    const routerDecision = spans.find(s => s.type === "router_decision")
    const turnComplete   = spans.find(s => s.type === "turn_complete")

    let userMessage = (routerDecision?.payload?.user_message as string | undefined) ?? null
    if (!userMessage) {
      const llmStart = spans.find(
        s => s.type === "llm_call_start" && Array.isArray(s.payload?.messages)
      )
      if (llmStart?.payload?.messages) {
        const msgs = llmStart.payload.messages as LLMMessage[]
        const userMsgs = msgs.filter(m => m.role === "user")
        if (userMsgs.length > 0) {
          const last = userMsgs[userMsgs.length - 1]
          userMessage = typeof last.content === "string"
            ? last.content
            : last.content != null ? JSON.stringify(last.content) : null
        }
      }
    }

    // Tool calls + results (paired by order)
    const toolCallSpans = spans.filter(s => s.type === "tool_call")
    const toolResultSpans = spans.filter(s => s.type === "tool_result")
    const toolCalls = toolCallSpans.map((tc, idx) => ({
      tool: String(tc.payload?.tool ?? "Tool"),
      arguments: tc.payload?.arguments as Record<string, unknown> | null ?? null,
      result: toolResultSpans[idx]
        ? String(toolResultSpans[idx].payload?.result_preview ?? "")
        : null,
    }))

    let assistantMessage = (turnComplete?.payload?.content as string | undefined) ?? null
    if (!assistantMessage) {
      const llmEnds = spans.filter(s => s.type === "llm_call_end" && s.payload?.output)
      const llmEnd = llmEnds[llmEnds.length - 1] ?? null
      assistantMessage = (llmEnd?.payload?.output as string | null | undefined) ?? null
    }

    const turnType     = (turnComplete?.payload?.turn_type as string | undefined) ?? null
    const inputTokens  = (turnComplete?.payload?.total_input_tokens as number | undefined) ?? 0
    const outputTokens = (turnComplete?.payload?.total_output_tokens as number | undefined) ?? 0
    const costUsd      = (turnComplete?.payload?.estimated_cost_usd as number | undefined) ?? 0

    // Only skip turns that have literally no content to show. A cancelled turn
    // with just a user message still gets rendered so the user can see it was
    // attempted.
    if (!userMessage && !assistantMessage && toolCalls.length === 0) {
      continue
    }

    turns.push({
      runId: run.id,
      runIndex: i + 1,
      userMessage,
      toolCalls,
      assistantMessage,
      turnType,
      inputTokens,
      outputTokens,
      costUsd,
    })
  }

  return turns
}

function extractUserMessage(run: RunDetail): string | null {
  const spans = [...run.spans].sort(
    (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
  )
  const routerDecision = spans.find(s => s.type === "router_decision")
  const fromRouter = routerDecision?.payload?.user_message as string | undefined
  if (fromRouter) return fromRouter

  const llmStart = spans.find(
    s => s.type === "llm_call_start" && Array.isArray(s.payload?.messages)
  )
  if (!llmStart?.payload?.messages) return null
  const msgs = llmStart.payload.messages as LLMMessage[]
  const userMsgs = msgs.filter(m => m.role === "user")
  if (userMsgs.length === 0) return null
  const last = userMsgs[userMsgs.length - 1]
  return typeof last.content === "string" ? last.content : null
}

// ── Chat tab ───────────────────────────────────────────────────────────────────

function ToolCallBlock({
  tool,
  arguments: args,
  result,
}: {
  tool: string
  arguments: Record<string, unknown> | null
  result: string | null
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="my-2 rounded-lg border border-amber-500/20 bg-amber-500/5 overflow-hidden text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-amber-500/10 transition-colors"
      >
        <Wrench className="size-3 text-amber-500 shrink-0" />
        <span className="font-medium text-amber-600">{tool}</span>
        <ChevronRight className={cn("size-3 text-amber-500/60 ml-auto transition-transform", open && "rotate-90")} />
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-amber-500/10">
          {args && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-600/70 mt-2 mb-1">Input</p>
              <pre className="font-mono text-[11px] text-foreground/80 whitespace-pre-wrap break-words">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          {result && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-600/70 mt-2 mb-1">Result</p>
              <pre className="font-mono text-[11px] text-foreground/70 whitespace-pre-wrap break-words">
                {result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ChatTurn({
  turn,
  projectId,
  spans,
  debugView,
}: {
  turn: ConversationTurn
  projectId: string
  spans: Span[]
  debugView: boolean
}) {
  return (
    <div className="space-y-3">
      {/* User bubble */}
      {turn.userMessage && (
        <div className="flex justify-end gap-3">
          <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-blue-500 px-4 py-2.5 text-sm text-white shadow-sm">
            {turn.userMessage}
          </div>
          <div className="flex-none w-7 h-7 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mt-0.5">
            <User className="size-3.5 text-blue-500" />
          </div>
        </div>
      )}

      {/* Tool calls */}
      {turn.toolCalls.length > 0 && (
        <div className="flex gap-3">
          <div className="flex-none w-7 h-7 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mt-0.5">
            <Wrench className="size-3.5 text-amber-500" />
          </div>
          <div className="flex-1 max-w-[75%]">
            {turn.toolCalls.map((tc, i) => (
              <ToolCallBlock key={i} tool={tc.tool} arguments={tc.arguments} result={tc.result} />
            ))}
          </div>
        </div>
      )}

      {/* Assistant bubble */}
      {turn.assistantMessage && (
        <div className="flex gap-3">
          <div className="flex-none w-7 h-7 rounded-full bg-muted border border-border flex items-center justify-center mt-0.5">
            <Bot className="size-3.5 text-muted-foreground" />
          </div>
          <div className="max-w-[75%] rounded-2xl rounded-tl-sm bg-card border border-border px-4 py-2.5 text-sm shadow-sm">
            <p className="whitespace-pre-wrap leading-relaxed">{turn.assistantMessage}</p>
          </div>
        </div>
      )}

      {/* Turn meta: tokens + cost + run link */}
      {(turn.inputTokens > 0 || turn.outputTokens > 0 || turn.costUsd > 0) && (
        <div className="flex items-center gap-3 pl-10">
          {(turn.inputTokens > 0 || turn.outputTokens > 0) && (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground/60">
              <Hash className="size-2.5" />
              {turn.inputTokens > 0 && turn.outputTokens > 0
                ? `${fmtTokens(turn.inputTokens)}↑ ${fmtTokens(turn.outputTokens)}↓`
                : fmtTokens(turn.inputTokens + turn.outputTokens)
              }
            </span>
          )}
          {turn.costUsd > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground/60">
              <Coins className="size-2.5" />
              {fmt_cost(turn.costUsd)}
            </span>
          )}
          <Link
            to={`/projects/${projectId}/traces/${turn.runId}`}
            className="flex items-center gap-0.5 text-[10px] text-muted-foreground/40 hover:text-muted-foreground transition-colors ml-auto"
          >
            Run {turn.runIndex}
            <ExternalLink className="size-2.5 ml-0.5" />
          </Link>
        </div>
      )}

      {debugView && spans.length > 0 && (
        <div className="pl-10">
          <TurnSpanPills spans={spans} />
        </div>
      )}
    </div>
  )
}

function ChatView({
  runs,
  projectId,
  debugView,
}: {
  runs: RunDetail[]
  projectId: string
  debugView: boolean
}) {
  const turns = extractTurns(runs)
  const spansByRun = new Map(runs.map(r => [r.id, r.spans] as const))

  if (turns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Bot className="size-10 text-muted-foreground/25 mb-3" />
        <p className="font-medium text-sm">No conversation found</p>
        <p className="text-sm text-muted-foreground mt-1 max-w-xs">
          Could not extract conversation messages from this session's spans.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto py-6 space-y-8">
      {turns.map((turn, i) => (
        <div key={turn.runId}>
          {i > 0 && <div className="border-t border-border/30 mb-8" />}
          <ChatTurn
            turn={turn}
            projectId={projectId}
            spans={spansByRun.get(turn.runId) ?? []}
            debugView={debugView}
          />
        </div>
      ))}
    </div>
  )
}

// ── Traces tab ─────────────────────────────────────────────────────────────────

function RunWaterfall({
  run,
  index,
  projectId,
}: {
  run: RunDetail
  index: number
  projectId: string
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [collapsed, setCollapsed] = useState(false)

  const toggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const runDurationMs = run.ended_at
    ? new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()
    : 0

  const sortedSpans = [...run.spans].sort(
    (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
  )
  const depths = buildDepthMap(run.spans)

  const userMessage = extractUserMessage(run)
  const toolCounts = toolCountsFromSpans(run.spans)
  const hasTools = Object.keys(toolCounts).length > 0

  return (
    <div className="border rounded-lg bg-card overflow-hidden">
      {/* Run header */}
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-muted/30 hover:bg-muted/50 transition-colors text-left border-b border-border/50"
      >
        <ChevronRight className={cn("size-3.5 text-muted-foreground/60 shrink-0 transition-transform", !collapsed && "rotate-90")} />
        <span className="text-xs font-medium text-muted-foreground shrink-0">
          Turn {index + 1}
        </span>
        <StatusBadge status={run.status} />
        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
          {fmtDur(run.started_at, run.ended_at)}
        </span>
        {userMessage && (
          <span className="text-xs text-muted-foreground/70 truncate max-w-[240px] italic">
            "{userMessage.length > 60 ? userMessage.slice(0, 60) + "…" : userMessage}"
          </span>
        )}
        {hasTools && (
          <ToolChips toolCounts={toolCounts} className="shrink-0" />
        )}
        <span className="ml-auto text-[11px] text-muted-foreground/50 font-mono shrink-0">
          {fmtRelative(run.started_at)}
        </span>
        <Link
          to={`/projects/${projectId}/traces/${run.id}`}
          onClick={e => e.stopPropagation()}
          className="flex items-center gap-1 text-[10px] text-muted-foreground/40 hover:text-muted-foreground transition-colors shrink-0"
        >
          <ExternalLink className="size-3" />
        </Link>
      </button>

      {/* Span waterfall */}
      {!collapsed && (
        <>
          <div className="px-4 pt-2 pb-0.5 flex items-center gap-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 select-none border-b border-border/30">
            <div className="w-72 shrink-0">Span</div>
            <div className="flex-1 px-4">Timeline</div>
            <div className="w-56 pr-2 text-right">Duration · Tokens · Cost</div>
          </div>

          <div className="px-2 py-1">
            {sortedSpans.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">No spans recorded.</p>
            ) : (
              sortedSpans.map((span, i) => (
                <div key={span.id} className={cn(i < sortedSpans.length - 1 && "border-b border-border/30")}>
                  <SpanRow
                    span={span}
                    depth={depths.get(span.id) ?? 0}
                    isLast={i === sortedSpans.length - 1}
                    runStart={run.started_at}
                    runDurationMs={runDurationMs}
                    expanded={expanded.has(span.id)}
                    onToggle={() => toggle(span.id)}
                    allSpans={sortedSpans}
                  />
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}

function TracesView({ runs, projectId }: { runs: RunDetail[]; projectId: string }) {
  return (
    <div className="space-y-4 py-4">
      {runs.map((run, i) => (
        <RunWaterfall key={run.id} run={run} index={i} projectId={projectId} />
      ))}
    </div>
  )
}

// ── Timeline tab (Gantt) ───────────────────────────────────────────────────────

const LABEL_COL_W = 200  // px — fixed label column width

interface GanttRow {
  span: Span
  runIndex: number
  leftPct: number   // % within timeline column
  widthPct: number  // % of timeline column; 0 = instant event (show tick)
  dotColor: string
  pillText: string
  pillColor: string
  label: string
  durMs: number | null
}

function buildGanttRows(
  runs: RunDetail[],
  sessionStartMs: number,
  sessionDurationMs: number,
): { groups: { run: RunDetail; runIndex: number; rows: GanttRow[] }[] } {
  const total = Math.max(sessionDurationMs, 1)
  const groups: { run: RunDetail; runIndex: number; rows: GanttRow[] }[] = []

  for (let ri = 0; ri < runs.length; ri++) {
    const run = runs[ri]
    const sortedSpans = [...run.spans].sort(
      (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
    )

    const rows: GanttRow[] = sortedSpans.map(span => {
      const cfg = SPAN_CONFIG[span.type] ?? DEFAULT_SPAN_CONFIG
      const spanStartMs = new Date(span.started_at).getTime()
      const durMs = span.duration_ms
        ?? (span.payload?.duration_ms as number | undefined)
        ?? (span.ended_at
            ? new Date(span.ended_at).getTime() - spanStartMs
            : null)

      const leftPct  = Math.max(0, Math.min(((spanStartMs - sessionStartMs) / total) * 100, 99.5))
      const widthPct = (durMs && durMs > 0)
        ? Math.max(0.8, Math.min((durMs / total) * 100, 100 - leftPct))
        : 0

      let label = cfg.label
      if ((span.type === "tool_call" || span.type === "tool_result") && span.payload?.tool) {
        label = String(span.payload.tool)
      } else if ((span.type === "llm_call_start" || span.type === "llm_call_end") && span.payload?.model) {
        label = String(span.payload.model)
      }

      return { span, runIndex: ri, leftPct, widthPct, dotColor: cfg.dotColor, pillText: cfg.pillText, pillColor: cfg.pillColor, label, durMs: durMs ?? null }
    })

    if (rows.length > 0) groups.push({ run, runIndex: ri, rows })
  }

  return { groups }
}

function TimelineView({ runs }: { runs: RunDetail[] }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  if (runs.length === 0) return null

  const sessionStartMs = Math.min(...runs.map(r => new Date(r.started_at).getTime()))
  const sessionEndMs   = Math.max(...runs.map(r =>
    r.ended_at ? new Date(r.ended_at).getTime() : Date.now()
  ))
  const sessionDurationMs = sessionEndMs - sessionStartMs

  const { groups } = buildGanttRows(runs, sessionStartMs, sessionDurationMs)

  // 5 evenly-spaced time axis ticks
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => ({
    pct: f * 100,
    label: f === 0 ? "0" : fmt_ms(f * sessionDurationMs),
  }))

  return (
    <div className="py-4 select-none">
      <div className="rounded-lg border bg-card overflow-hidden">

        {/* ── Column header row ── */}
        <div className="flex border-b border-border/50 bg-muted/30">
          {/* Label column header */}
          <div
            className="shrink-0 flex items-center px-3 py-2 border-r border-border/40"
            style={{ width: LABEL_COL_W }}
          >
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              Span
            </span>
          </div>

          {/* Time axis */}
          <div className="relative flex-1 h-8">
            {ticks.map(tick => (
              <div
                key={tick.pct}
                className="absolute top-0 bottom-0 flex flex-col justify-end pb-1"
                style={{ left: `${tick.pct}%` }}
              >
                <div className="w-px h-2 bg-border/50 mb-0.5" />
                <span className="text-[9px] tabular-nums text-muted-foreground/50 leading-none -translate-x-1/2">
                  {tick.label}
                </span>
              </div>
            ))}
            {/* Horizontal baseline */}
            <div className="absolute bottom-0 left-0 right-0 h-px bg-border/30" />
          </div>
        </div>

        {/* ── Run groups ── */}
        {groups.map(({ run, runIndex, rows }, gi) => (
          <div key={run.id} className={cn(gi > 0 && "border-t border-border/40")}>

            {/* Run separator row */}
            <div className="flex items-center gap-2.5 px-3 py-2 bg-muted/20 border-b border-border/30">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                Run {runIndex + 1}
              </span>
              <StatusBadge status={run.status} />
              <span className="text-[10px] tabular-nums text-muted-foreground/50">
                {fmtDur(run.started_at, run.ended_at)}
              </span>
              <span className="text-[10px] tabular-nums text-muted-foreground/40 ml-auto">
                {rows.length} spans
              </span>
            </div>

            {/* Span rows */}
            {rows.map((row, si) => {
              const isHovered = hoveredId === row.span.id
              const isLast = si === rows.length - 1

              return (
                <div
                  key={row.span.id}
                  className={cn(
                    "flex items-stretch transition-colors",
                    !isLast && "border-b border-border/20",
                    isHovered ? "bg-muted/40" : "hover:bg-muted/20"
                  )}
                  onMouseEnter={() => setHoveredId(row.span.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  {/* Label column */}
                  <div
                    className="shrink-0 flex items-center gap-2 px-3 py-1.5 border-r border-border/30"
                    style={{ width: LABEL_COL_W }}
                  >
                    <span className={cn(
                      "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold leading-none",
                      row.pillColor
                    )}>
                      {row.pillText}
                    </span>
                    <span className="text-xs text-foreground/80 truncate">{row.label}</span>
                  </div>

                  {/* Timeline bar area */}
                  <div className="relative flex-1 flex items-center min-h-[32px]">
                    {/* Tick grid lines (subtle) */}
                    {ticks.slice(1).map(tick => (
                      <div
                        key={tick.pct}
                        className="absolute top-0 bottom-0 w-px bg-border/10"
                        style={{ left: `${tick.pct}%` }}
                      />
                    ))}

                    {row.widthPct > 0 ? (
                      /* Duration bar */
                      <div
                        className="absolute rounded-sm"
                        style={{
                          left: `${row.leftPct}%`,
                          width: `${row.widthPct}%`,
                          top: "30%",
                          bottom: "30%",
                          backgroundColor: row.dotColor,
                          opacity: isHovered ? 0.9 : 0.65,
                        }}
                      />
                    ) : (
                      /* Instant event — vertical tick */
                      <div
                        className="absolute rounded-full"
                        style={{
                          left: `calc(${row.leftPct}% - 3px)`,
                          top: "25%",
                          bottom: "25%",
                          width: 6,
                          backgroundColor: row.dotColor,
                          opacity: isHovered ? 0.9 : 0.7,
                        }}
                      />
                    )}

                    {/* Duration label — shown inside bar when wide enough, else to the right */}
                    {row.durMs != null && row.durMs > 0 && (
                      <span
                        className="absolute text-[9px] tabular-nums font-medium pointer-events-none whitespace-nowrap"
                        style={{
                          left: `calc(${row.leftPct + row.widthPct}% + 4px)`,
                          color: "var(--muted-foreground)",
                          opacity: 0.7,
                          top: "50%",
                          transform: "translateY(-50%)",
                        }}
                      >
                        {fmt_ms(row.durMs)}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Session header ─────────────────────────────────────────────────────────────

function SessionHeader({ session }: { session: SessionDetailType }) {
  const allRuns = session.runs
  const totalTokens = allRuns.reduce((s, r) => s + r.total_tokens, 0)
  const totalCost   = allRuns.reduce((s, r) => s + r.total_cost_usd, 0)
  const started = allRuns[0]?.started_at ?? ""
  const ended   = allRuns.every(r => r.ended_at)
    ? allRuns[allRuns.length - 1].ended_at
    : null

  const status: RunStatus = allRuns.some(r => r.status === "running")
    ? "running"
    : allRuns.some(r => r.status === "failed")
    ? "failed"
    : "completed"

  return (
    <div className="border-b bg-muted/20 px-6 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={status} />

        <div className="w-px h-4 bg-border" />

        <span className="flex items-center gap-1 text-sm">
          <Layers className="size-3.5 text-muted-foreground shrink-0" />
          <span className="tabular-nums font-medium">{allRuns.length}</span>
          <span className="text-muted-foreground text-xs">{allRuns.length === 1 ? "run" : "runs"}</span>
        </span>

        {started && (
          <span className="flex items-center gap-1 text-sm">
            <Clock className="size-3.5 text-muted-foreground shrink-0" />
            <span className="tabular-nums font-medium">{fmtDur(started, ended)}</span>
          </span>
        )}

        <span className="flex items-center gap-1 text-sm">
          <Hash className="size-3.5 text-muted-foreground shrink-0" />
          <span className="tabular-nums font-medium">{fmtTokens(totalTokens)}</span>
          <span className="text-muted-foreground text-xs">tokens</span>
        </span>

        <span className="flex items-center gap-1 text-sm">
          <Coins className="size-3.5 text-muted-foreground shrink-0" />
          <span className="tabular-nums font-medium">{fmt_cost(totalCost) || "$0"}</span>
        </span>
      </div>

      {started && (
        <div className="mt-1.5 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
          <span>Started {new Date(started).toLocaleString()}</span>
          {ended && <span>Ended {new Date(ended).toLocaleString()}</span>}
          <span className="font-mono text-muted-foreground/50">{session.session_id}</span>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export function SessionDetail() {
  const { projectId, sessionId } = useParams<{ projectId: string; sessionId: string }>()

  const [session, setSession] = useState<SessionDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"chat" | "traces" | "timeline">("chat")
  const [goldenOpen, setGoldenOpen] = useState(false)
  const [debugView, setDebugView] = useDebugView()

  useEffect(() => {
    if (!projectId || !sessionId) return
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const data = await api.get<SessionDetailType>(
          `/projects/${projectId}/sessions/${sessionId}`
        )
        if (!cancelled) { setSession(data); setLoading(false) }
      } catch (e) {
        if (!cancelled) { setError((e as Error).message); setLoading(false) }
      }
    }
    load()
    return () => { cancelled = true }
  }, [projectId, sessionId])

  const breadcrumb = (
    <div className="flex items-center gap-2 text-sm min-w-0">
      <Link
        to={`/projects/${projectId}/traces`}
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
      >
        <ChevronLeft className="size-3.5" />
        Traces
      </Link>
      {session && (
        <>
          <span className="text-border">/</span>
          <span className="font-semibold truncate max-w-[300px]">
            {session.agent_name ?? "Session"}
          </span>
          <span className="text-muted-foreground/50 text-xs font-mono shrink-0">
            ·{session.session_id.slice(-8).toUpperCase()}
          </span>
        </>
      )}
    </div>
  )

  return (
    <>
      <TopBar
        title={breadcrumb}
        actions={session && (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDebugView(!debugView)}
              aria-pressed={debugView}
              className={debugView ? "bg-muted text-foreground" : "text-muted-foreground"}
              title={debugView ? "Hide internal span pills" : "Show internal span pills under each turn"}
            >
              <Bug className="size-3.5 mr-1.5" />
              Debug view
            </Button>
            <Button size="sm" variant="outline" onClick={() => setGoldenOpen(true)}>
              <BookOpen className="size-3.5 mr-1.5" />
              Add to Dataset
            </Button>
          </div>
        )}
      />

      {session && goldenOpen && (
        <SaveAsGoldenDialog
          open={goldenOpen}
          onClose={() => setGoldenOpen(false)}
          source={{ kind: "session", sessionId: session.session_id }}
        />
      )}

      <main className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-6 space-y-3">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-8 w-64 rounded" />
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        ) : error ? (
          <div className="p-6">
            <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              <AlertCircle className="size-4 shrink-0" />
              {error}
            </div>
          </div>
        ) : !session ? null : (
          <>
            <SessionHeader session={session} />

            <div className="px-6 pt-4 pb-8">
              <Tabs
                value={activeTab}
                onValueChange={v => setActiveTab(v as "chat" | "traces" | "timeline")}
              >
                <TabsList variant="line" className="mb-4">
                  <TabsTrigger value="chat">Chat</TabsTrigger>
                  <TabsTrigger value="traces">Traces</TabsTrigger>
                  <TabsTrigger value="timeline">Timeline</TabsTrigger>
                </TabsList>

                <TabsContent value="chat">
                  <ChatView runs={session.runs} projectId={projectId!} debugView={debugView} />
                </TabsContent>

                <TabsContent value="traces">
                  <TracesView runs={session.runs} projectId={projectId!} />
                </TabsContent>

                <TabsContent value="timeline">
                  <TimelineView runs={session.runs} />
                </TabsContent>
              </Tabs>
            </div>
          </>
        )}
      </main>
    </>
  )
}
