/**
 * Shared span waterfall components extracted from TraceDetail.
 * Used by both TraceDetail (single-run) and SessionDetail (multi-run traces tab).
 */

import { cn } from "@/lib/utils"
import type { Span, SpanType, LLMMessage, LLMToolCall } from "@/types/trace"
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Cpu,
  FormInput,
  GitBranch,
  Wrench,
  Zap,
} from "lucide-react"

// ── Formatting ─────────────────────────────────────────────────────────────────

export function fmt_ms(ms: number | null | undefined): string {
  if (ms == null) return "—"
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function fmt_cost(usd: number | null | undefined): string {
  if (!usd) return ""
  if (usd < 0.0001) return "<$0.0001"
  return `$${usd.toFixed(4)}`
}

export function fmt_offset(iso: string, runStart: string): string {
  const ms = new Date(iso).getTime() - new Date(runStart).getTime()
  if (ms <= 0) return "+0ms"
  if (ms < 1000) return `+${ms}ms`
  return `+${(ms / 1000).toFixed(2)}s`
}

export function fmt_tokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

// ── Span type config ───────────────────────────────────────────────────────────

export interface SpanConfig {
  icon: React.ElementType
  dotColor: string
  pillText: string
  pillColor: string
  label: string
}

// Color philosophy: errors use red (semantic), everything else is neutral muted.
// The span TYPE is conveyed by the label text — color shouldn't compete for attention.
// Dot colors are kept distinct only for the timeline waterfall view.
const NEUTRAL_PILL = "bg-muted text-foreground"
const ERROR_PILL = "bg-red-500/10 text-red-600"

export const SPAN_CONFIG: Record<string, SpanConfig> = {
  router_start: {
    icon: GitBranch, dotColor: "#8b5cf6",
    pillText: "router", pillColor: NEUTRAL_PILL,
    label: "Router",
  },
  router_decision: {
    icon: GitBranch, dotColor: "#7c3aed",
    pillText: "router", pillColor: NEUTRAL_PILL,
    label: "Router Decision",
  },
  llm_call_start: {
    icon: Cpu, dotColor: "#3b82f6",
    pillText: "llm", pillColor: NEUTRAL_PILL,
    label: "LLM Call",
  },
  llm_call_end: {
    icon: Cpu, dotColor: "#2563eb",
    pillText: "llm", pillColor: NEUTRAL_PILL,
    label: "LLM Response",
  },
  tool_call: {
    icon: Wrench, dotColor: "#f59e0b",
    pillText: "tool", pillColor: NEUTRAL_PILL,
    label: "Tool Call",
  },
  tool_result: {
    icon: Wrench, dotColor: "#d97706",
    pillText: "tool", pillColor: NEUTRAL_PILL,
    label: "Tool Result",
  },
  slot_fill: {
    icon: FormInput, dotColor: "#06b6d4",
    pillText: "slot", pillColor: NEUTRAL_PILL,
    label: "Slot Fill",
  },
  interrupt_triggered: {
    icon: Zap, dotColor: "#ef4444",
    pillText: "interrupt", pillColor: NEUTRAL_PILL,
    label: "Interrupt",
  },
  handoff_triggered: {
    icon: ArrowRightLeft, dotColor: "#f97316",
    pillText: "handoff", pillColor: NEUTRAL_PILL,
    label: "Handoff",
  },
  turn_complete: {
    icon: CheckCircle2, dotColor: "#10b981",
    pillText: "complete", pillColor: NEUTRAL_PILL,
    label: "Turn Complete",
  },
  router_parse_error: {
    icon: AlertTriangle, dotColor: "#dc2626",
    pillText: "error", pillColor: ERROR_PILL,
    label: "Router Parse Error",
  },
  tool_loop_exceeded: {
    icon: AlertTriangle, dotColor: "#dc2626",
    pillText: "error", pillColor: ERROR_PILL,
    label: "Tool Loop Exceeded",
  },
  tool_error: {
    icon: AlertTriangle, dotColor: "#dc2626",
    pillText: "error", pillColor: ERROR_PILL,
    label: "Tool Error",
  },
}

export const DEFAULT_SPAN_CONFIG: SpanConfig = {
  icon: Circle, dotColor: "#6b7280",
  pillText: "span", pillColor: NEUTRAL_PILL,
  label: "Span",
}

export function getSpanConfig(type: SpanType): SpanConfig {
  return SPAN_CONFIG[type] ?? DEFAULT_SPAN_CONFIG
}

// ── Tool helpers ───────────────────────────────────────────────────────────────

export function toolCountsFromSpans(spans: Span[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const s of spans) {
    if (s.type === "tool_call") {
      const name = String(s.payload?.tool ?? "tool")
      counts[name] = (counts[name] ?? 0) + 1
    }
  }
  return counts
}

export function ToolChips({
  toolCounts,
  className,
}: {
  toolCounts: Record<string, number>
  className?: string
}) {
  const entries = Object.entries(toolCounts)
  if (entries.length === 0) return null
  return (
    <div className={cn("flex items-center gap-1.5 flex-wrap", className)}>
      {entries.map(([name, count]) => (
        <span
          key={name}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/10 text-amber-600"
        >
          <Wrench className="size-2.5" />
          {name}{count > 1 ? ` ×${count}` : ""}
        </span>
      ))}
    </div>
  )
}

// ── Depth map ──────────────────────────────────────────────────────────────────

export function buildDepthMap(spans: Span[]): Map<string, number> {
  const parentOf = new Map(spans.map(s => [s.id, s.parent_span_id]))
  const depths = new Map<string, number>()

  function depth(id: string): number {
    if (depths.has(id)) return depths.get(id)!
    const parent = parentOf.get(id)
    if (!parent) { depths.set(id, 0); return 0 }
    const d = depth(parent) + 1
    depths.set(id, d)
    return d
  }

  spans.forEach(s => depth(s.id))
  return depths
}

// ── Timeline bar ───────────────────────────────────────────────────────────────

export function TimelineBar({
  span,
  runStart,
  runDurationMs,
  dotColor,
}: {
  span: Span
  runStart: string
  runDurationMs: number
  dotColor: string
}) {
  const spanStartMs = new Date(span.started_at).getTime()
  const runStartMs  = new Date(runStart).getTime()
  const totalMs = Math.max(runDurationMs, 1)

  const leftPct = Math.max(0, Math.min(((spanStartMs - runStartMs) / totalMs) * 100, 98))

  const durMs = span.duration_ms
    ?? (span.payload?.duration_ms as number | undefined)
    ?? 0
  const barPct = durMs > 0
    ? Math.max(1, (durMs / totalMs) * 100)
    : 0

  return (
    <div className="relative flex-1 h-5 min-w-0 flex items-center">
      <div className="absolute inset-y-[9px] left-0 right-0 bg-border/40 rounded-full h-px" />

      {barPct > 0 && (
        <div
          className="absolute top-[7px] h-[6px] rounded-full opacity-50"
          style={{
            left: `${leftPct}%`,
            width: `${Math.min(barPct, 100 - leftPct)}%`,
            backgroundColor: dotColor,
          }}
        />
      )}

      <div
        className="absolute top-[7px] size-[6px] rounded-full ring-[2px] ring-background z-10"
        style={{
          left: `calc(${leftPct}% - 3px)`,
          backgroundColor: dotColor,
        }}
      />
    </div>
  )
}

// ── Structured detail panels ───────────────────────────────────────────────────

function LLMMessagesPanel({ messages }: { messages: LLMMessage[] }) {
  const ROLE_META: Record<string, { label: string; color: string; border: string }> = {
    system:    { label: "system",      color: "text-violet-500",  border: "border-violet-500/20" },
    user:      { label: "user",        color: "text-blue-500",    border: "border-blue-500/20"   },
    assistant: { label: "assistant",   color: "text-emerald-600", border: "border-emerald-500/20" },
    tool:      { label: "tool result", color: "text-amber-600",   border: "border-amber-500/20"  },
  }

  return (
    <div className="space-y-2.5">
      {messages.map((msg, i) => {
        const meta = ROLE_META[msg.role] ?? { label: msg.role, color: "text-muted-foreground", border: "border-border/50" }

        if (msg.role === "assistant" && msg.tool_calls?.length) {
          return (
            <div key={i}>
              <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-1", meta.color)}>
                {meta.label} — tool call{msg.tool_calls.length > 1 ? "s" : ""}
              </div>
              <div className={cn("rounded bg-background border p-2.5 space-y-2", meta.border)}>
                {msg.tool_calls.map((tc, j) => (
                  <div key={j}>
                    <div className="text-[11px] font-semibold text-amber-600 mb-1">{tc.function.name}</div>
                    <pre className="font-mono text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-words">
                      {(() => { try { return JSON.stringify(JSON.parse(tc.function.arguments), null, 2) } catch { return tc.function.arguments } })()}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )
        }

        if (msg.role === "tool") {
          return (
            <div key={i}>
              <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-1", meta.color)}>
                {meta.label}{msg.tool_call_id ? ` · ${msg.tool_call_id.slice(0, 12)}…` : ""}
              </div>
              <div className={cn("rounded bg-background border p-2.5 max-h-40 overflow-y-auto", meta.border)}>
                <pre className="font-mono text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-words">
                  {typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content, null, 2)}
                </pre>
              </div>
            </div>
          )
        }

        const content = msg.content
        return (
          <div key={i}>
            <div className={cn("text-[10px] font-semibold uppercase tracking-wider mb-1", meta.color)}>
              {meta.label}
            </div>
            <div className={cn("rounded bg-background border p-2.5 max-h-64 overflow-y-auto", meta.border)}>
              <pre className="font-mono text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-words">
                {typeof content === "string"
                  ? content
                  : content == null ? "(empty)" : JSON.stringify(content, null, 2)}
              </pre>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function LLMOutputPanel({
  output,
  toolCalls,
  stopReason,
}: {
  output?: string | null
  toolCalls?: LLMToolCall[] | null
  stopReason?: string
}) {
  return (
    <div className="space-y-3">
      {output && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 text-emerald-600">
            response
            {stopReason && (
              <span className="ml-2 font-normal normal-case text-muted-foreground">
                stop_reason: {stopReason}
              </span>
            )}
          </div>
          <div className="rounded bg-background border border-border/50 p-2.5 max-h-64 overflow-y-auto">
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground/80">
              {output}
            </pre>
          </div>
        </div>
      )}

      {toolCalls && toolCalls.length > 0 && toolCalls.map((tc, i) => (
        <div key={i}>
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 text-amber-600">
            tool call — {tc.name}
          </div>
          <div className="rounded bg-background border border-amber-500/20 p-2.5 overflow-x-auto">
            <pre className="font-mono text-[11px] leading-relaxed text-foreground/80">
              {JSON.stringify(tc.arguments, null, 2)}
            </pre>
          </div>
        </div>
      ))}

      {!output && (!toolCalls || toolCalls.length === 0) && (
        <p className="text-xs text-muted-foreground italic">No output captured.</p>
      )}
    </div>
  )
}

function RouterDecisionPanel({
  decision,
  prompt,
  systemPrompt,
}: {
  decision: Record<string, unknown>
  prompt?: string | null
  systemPrompt?: string | null
}) {
  const FIELDS = [
    ["active_condition", "Condition"],
    ["active_goal",      "Goal"],
    ["reasoning",        "Reasoning"],
    ["interrupt_triggered", "Interrupt"],
    ["handoff_triggered",   "Handoff"],
    ["sub_agent",           "Sub-agent"],
    ["unfilled_slots",      "Unfilled slots"],
  ] as const

  const meaningful = FIELDS.filter(([key]) => {
    const v = decision[key]
    return v != null && v !== "" && !(Array.isArray(v) && v.length === 0)
  })

  return (
    <div className="space-y-3">
      {meaningful.length > 0 && (
        <div className="rounded bg-background border border-border/50 divide-y divide-border/40">
          {meaningful.map(([key, label]) => (
            <div key={key} className="flex gap-3 px-3 py-1.5">
              <span className="text-[11px] text-muted-foreground w-28 shrink-0">{label}</span>
              <span className="text-[11px] font-medium break-words">
                {Array.isArray(decision[key])
                  ? (decision[key] as unknown[]).join(", ")
                  : String(decision[key])}
              </span>
            </div>
          ))}
        </div>
      )}

      {systemPrompt && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 text-violet-500">
            router system prompt
          </div>
          <div className="rounded bg-background border border-border/50 p-2.5 max-h-48 overflow-y-auto">
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground/80">
              {systemPrompt}
            </pre>
          </div>
        </div>
      )}

      {prompt && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 text-violet-500">
            routing prompt
          </div>
          <div className="rounded bg-background border border-border/50 p-2.5 max-h-48 overflow-y-auto">
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground/80">
              {prompt}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Section header used inside detail panels ──────────────────────────────────

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider mb-2 text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  )
}

export function SpanDetailPanel({ span, allSpans }: { span: Span; allSpans?: Span[] }) {
  const p = span.payload ?? {}

  if (span.type === "turn_complete") {
    const toolCounts = toolCountsFromSpans(allSpans ?? [])
    const hasTools = Object.keys(toolCounts).length > 0
    return (
      <div className="space-y-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          tools called
        </div>
        {hasTools
          ? <ToolChips toolCounts={toolCounts} />
          : <p className="text-xs text-muted-foreground italic">No tools called this turn.</p>
        }
      </div>
    )
  }

  // ── Merged LLM call view (start + end paired by iteration) ────────────────
  if (span.type === "llm_call_end" || span.type === "llm_call_start") {
    const endSpan = span.type === "llm_call_end"
      ? span
      : allSpans?.find(s => s.type === "llm_call_end" && s.payload?.iteration === p.iteration) ?? null
    const startSpan = span.type === "llm_call_start"
      ? span
      : allSpans?.find(s => s.type === "llm_call_start" && s.payload?.iteration === p.iteration) ?? null

    const startP = startSpan?.payload ?? {}
    const endP = endSpan?.payload ?? {}

    const messages = startP.messages as LLMMessage[] | undefined
    const output = endP.output as string | null | undefined
    const toolCalls = endP.tool_calls as LLMToolCall[] | null | undefined
    const stopReason = endP.stop_reason as string | undefined

    return (
      <div className="space-y-4">
        {/* Stats summary */}
        <LLMStatsHeader
          model={endP.model as string | undefined}
          inputTokens={endP.input_tokens as number | undefined}
          outputTokens={endP.output_tokens as number | undefined}
          durationMs={endSpan?.duration_ms ?? null}
          stopReason={stopReason}
        />

        {messages && messages.length > 0 && (
          <PanelSection title={`Input (${messages.length} ${messages.length === 1 ? "message" : "messages"})`}>
            <LLMMessagesPanel messages={messages} />
          </PanelSection>
        )}

        {(output || (toolCalls && toolCalls.length > 0)) && (
          <PanelSection title="Output">
            <LLMOutputPanel
              output={output}
              toolCalls={toolCalls}
              stopReason={stopReason}
            />
          </PanelSection>
        )}

        {!messages && !output && (!toolCalls || toolCalls.length === 0) && (
          <p className="text-xs text-muted-foreground italic">No payload captured.</p>
        )}
      </div>
    )
  }

  if (span.type === "router_decision" && p.decision) {
    return (
      <RouterDecisionPanel
        decision={p.decision as Record<string, unknown>}
        prompt={p.prompt as string | null}
        systemPrompt={p.system_prompt as string | null}
      />
    )
  }

  // ── Merged tool call view (call + result/error paired) ────────────────────
  if (span.type === "tool_call" || span.type === "tool_result" || span.type === "tool_error") {
    const callSpan = span.type === "tool_call"
      ? span
      : allSpans?.find(s => s.type === "tool_call" && s.id === span.parent_span_id) ?? null
    const resultSpan = span.type === "tool_call"
      ? allSpans?.find(s => (s.type === "tool_result" || s.type === "tool_error") && s.parent_span_id === span.id) ?? null
      : span

    const callP = callSpan?.payload ?? {}
    const resultP = resultSpan?.payload ?? {}
    const toolName = (callP.tool ?? resultP.tool ?? p.tool) as string | undefined
    const args = callP.arguments as Record<string, unknown> | undefined
    const isError = resultSpan?.type === "tool_error"

    return (
      <div className="space-y-4">
        <ToolStatsHeader
          toolName={toolName}
          durationMs={resultSpan?.duration_ms ?? callSpan?.duration_ms ?? null}
          isError={isError}
        />

        {args && Object.keys(args).length > 0 && (
          <PanelSection title="Arguments">
            <div className="rounded bg-background border border-border/50 p-2.5 overflow-x-auto">
              <pre className="font-mono text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-words">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          </PanelSection>
        )}

        {resultSpan && (
          <PanelSection title={isError ? "Error" : "Result"}>
            <div className={cn(
              "rounded border p-2.5 overflow-x-auto max-h-64 overflow-y-auto",
              isError ? "bg-red-500/5 border-red-500/20" : "bg-background border-border/50",
            )}>
              <pre className={cn(
                "font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all",
                isError ? "text-red-600" : "text-foreground/80",
              )}>
                {isError
                  ? String(resultP.error ?? "(no error message)")
                  : (typeof resultP.result_preview === "string"
                      ? resultP.result_preview
                      : JSON.stringify(resultP, null, 2))
                }
              </pre>
            </div>
          </PanelSection>
        )}
      </div>
    )
  }

  return (
    <pre className="font-mono text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap break-all">
      {JSON.stringify(p, null, 2)}
    </pre>
  )
}

// ── Stats headers ──────────────────────────────────────────────────────────────

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <span className="text-[10px] uppercase tracking-wide">{label}</span>
      <span className="font-medium text-foreground tabular-nums">{value}</span>
    </span>
  )
}

function LLMStatsHeader({
  model, inputTokens, outputTokens, durationMs, stopReason,
}: {
  model?: string
  inputTokens?: number
  outputTokens?: number
  durationMs: number | null
  stopReason?: string
}) {
  const pills: Array<{ label: string; value: string }> = []
  if (model) pills.push({ label: "model", value: model })
  if (inputTokens != null) pills.push({ label: "in", value: fmt_tokens(inputTokens) })
  if (outputTokens != null) pills.push({ label: "out", value: fmt_tokens(outputTokens) })
  if (durationMs != null) pills.push({ label: "took", value: fmt_ms(durationMs) })
  if (stopReason) pills.push({ label: "stop", value: stopReason })

  if (pills.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-3 border-b border-border/40">
      {pills.map(p => <StatPill key={p.label} label={p.label} value={p.value} />)}
    </div>
  )
}

function ToolStatsHeader({
  toolName, durationMs, isError,
}: {
  toolName?: string
  durationMs: number | null
  isError: boolean
}) {
  const pills: Array<{ label: string; value: string }> = []
  if (toolName) pills.push({ label: "tool", value: toolName })
  if (durationMs != null) pills.push({ label: "took", value: fmt_ms(durationMs) })
  if (isError) pills.push({ label: "status", value: "error" })

  if (pills.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-3 border-b border-border/40">
      {pills.map(p => <StatPill key={p.label} label={p.label} value={p.value} />)}
    </div>
  )
}

// ── Span row ───────────────────────────────────────────────────────────────────

export function SpanRow({
  span,
  depth,
  isLast,
  runStart,
  runDurationMs,
  expanded,
  onToggle,
  allSpans,
}: {
  span: Span
  depth: number
  isLast: boolean
  runStart: string
  runDurationMs: number
  expanded: boolean
  onToggle: () => void
  allSpans?: Span[]
}) {
  const cfg   = getSpanConfig(span.type)
  const Icon  = cfg.icon
  const p     = span.payload ?? {}

  let label = cfg.label
  if ((span.type === "tool_call" || span.type === "tool_result") && p.tool) {
    label = String(p.tool)
  } else if ((span.type === "llm_call_start" || span.type === "llm_call_end") && p.model) {
    label = String(p.model)
  } else if (span.type === "slot_fill" && p.slot_name) {
    label = `Slot: ${p.slot_name}`
  } else if (span.type === "router_decision" && p.decision) {
    const d = p.decision as Record<string, unknown>
    if (d.active_condition || d.active_goal) {
      label = [d.active_condition, d.active_goal].filter(Boolean).join(" → ") || cfg.label
    }
  }

  const inTok   = p.input_tokens  as number | undefined
  const outTok  = p.output_tokens as number | undefined
  const cost    = p.cost_usd      as number | undefined
  const hasTokens = inTok != null || outTok != null

  const durMs = span.duration_ms
    ?? (p.duration_ms as number | undefined)
    ?? (span.ended_at
        ? new Date(span.ended_at).getTime() - new Date(span.started_at).getTime()
        : null)

  const hasPayload = Object.keys(p).length > 0 || span.type === "turn_complete"
  const ToggleIcon = expanded ? ChevronDown : ChevronRight

  return (
    <div className="group">
      <button
        onClick={onToggle}
        className={cn(
          "w-full flex items-center gap-0 text-left transition-colors",
          "hover:bg-muted/40 rounded",
          expanded && "bg-muted/20"
        )}
      >
        <div className="flex shrink-0" style={{ width: depth * 20 }} />

        <div className="relative flex flex-col items-center shrink-0 w-6 self-stretch">
          {depth > 0 && (
            <div className="absolute top-0 bottom-1/2 left-1/2 w-px bg-border/50 -translate-x-1/2" />
          )}
          {!isLast && (
            <div className="absolute top-1/2 bottom-0 left-1/2 w-px bg-border/30 -translate-x-1/2" />
          )}
          <div
            className="relative z-10 mt-3.5 size-2 rounded-full ring-2 ring-background shrink-0"
            style={{ backgroundColor: cfg.dotColor }}
          />
        </div>

        <Icon className="size-3.5 shrink-0 ml-1.5 mr-2" style={{ color: cfg.dotColor }} />

        <span className={cn(
          "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-none mr-2",
          cfg.pillColor
        )}>
          {cfg.pillText}
        </span>

        <div className="flex items-baseline gap-2 min-w-0 w-52 shrink-0">
          <span className="text-xs font-medium truncate">{label}</span>
          <span className="text-[10px] text-muted-foreground/60 shrink-0 tabular-nums">
            {fmt_offset(span.started_at, runStart)}
          </span>
        </div>

        <div className="flex-1 px-4 min-w-0 py-3">
          <TimelineBar
            span={span}
            runStart={runStart}
            runDurationMs={runDurationMs}
            dotColor={cfg.dotColor}
          />
        </div>

        <div className="flex items-center gap-2 shrink-0 w-56 justify-end pr-2 py-2.5">
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {fmt_ms(durMs)}
          </span>

          {hasTokens && (
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] bg-blue-500/8 text-blue-500 tabular-nums font-medium">
              {inTok != null && outTok != null ? (
                <>{fmt_tokens(inTok)}<span className="opacity-50">↑</span>{fmt_tokens(outTok)}<span className="opacity-50">↓</span></>
              ) : (
                fmt_tokens((inTok ?? 0) + (outTok ?? 0))
              )}
            </span>
          )}

          {cost != null && cost > 0 && (
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-amber-500/8 text-amber-600 tabular-nums font-medium">
              {fmt_cost(cost)}
            </span>
          )}

          {hasPayload && (
            <ToggleIcon className="size-3.5 text-muted-foreground/40 shrink-0" />
          )}
        </div>
      </button>

      {expanded && hasPayload && (
        <div
          className="mb-1 rounded border border-border/50 bg-muted/20 p-3"
          style={{ marginLeft: depth * 20 + 56, marginRight: 8 }}
        >
          <SpanDetailPanel span={span} allSpans={allSpans} />
        </div>
      )}
    </div>
  )
}
