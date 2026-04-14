/**
 * Shared span waterfall components extracted from TraceDetail.
 * Used by both TraceDetail (single-run) and SessionDetail (multi-run traces tab).
 */

import { cn } from "@/lib/utils"
import type { Span, SpanType, LLMMessage, LLMToolCall } from "@/types/trace"
import {
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

export const SPAN_CONFIG: Record<string, SpanConfig> = {
  router_start: {
    icon: GitBranch, dotColor: "#8b5cf6",
    pillText: "router", pillColor: "bg-violet-500/10 text-violet-500",
    label: "Router",
  },
  router_decision: {
    icon: GitBranch, dotColor: "#7c3aed",
    pillText: "router", pillColor: "bg-violet-500/10 text-violet-500",
    label: "Router Decision",
  },
  llm_call_start: {
    icon: Cpu, dotColor: "#3b82f6",
    pillText: "llm", pillColor: "bg-blue-500/10 text-blue-500",
    label: "LLM Call",
  },
  llm_call_end: {
    icon: Cpu, dotColor: "#2563eb",
    pillText: "llm", pillColor: "bg-blue-500/10 text-blue-500",
    label: "LLM Response",
  },
  tool_call: {
    icon: Wrench, dotColor: "#f59e0b",
    pillText: "tool", pillColor: "bg-amber-500/10 text-amber-600",
    label: "Tool Call",
  },
  tool_result: {
    icon: Wrench, dotColor: "#d97706",
    pillText: "tool", pillColor: "bg-amber-500/10 text-amber-600",
    label: "Tool Result",
  },
  slot_fill: {
    icon: FormInput, dotColor: "#06b6d4",
    pillText: "slot", pillColor: "bg-cyan-500/10 text-cyan-600",
    label: "Slot Fill",
  },
  interrupt_triggered: {
    icon: Zap, dotColor: "#ef4444",
    pillText: "interrupt", pillColor: "bg-red-500/10 text-red-500",
    label: "Interrupt",
  },
  handoff_triggered: {
    icon: ArrowRightLeft, dotColor: "#f97316",
    pillText: "handoff", pillColor: "bg-orange-500/10 text-orange-600",
    label: "Handoff",
  },
  turn_complete: {
    icon: CheckCircle2, dotColor: "#10b981",
    pillText: "complete", pillColor: "bg-emerald-500/10 text-emerald-600",
    label: "Turn Complete",
  },
}

export const DEFAULT_SPAN_CONFIG: SpanConfig = {
  icon: Circle, dotColor: "#6b7280",
  pillText: "span", pillColor: "bg-muted text-muted-foreground",
  label: "Span",
}

export function getSpanConfig(type: SpanType): SpanConfig {
  return SPAN_CONFIG[type] ?? DEFAULT_SPAN_CONFIG
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
}: {
  decision: Record<string, unknown>
  prompt?: string | null
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

export function SpanDetailPanel({ span }: { span: Span }) {
  const p = span.payload ?? {}

  if (span.type === "llm_call_start" && p.messages) {
    return <LLMMessagesPanel messages={p.messages as LLMMessage[]} />
  }

  if (span.type === "llm_call_end") {
    return (
      <LLMOutputPanel
        output={p.output as string | null}
        toolCalls={p.tool_calls as LLMToolCall[] | null}
        stopReason={p.stop_reason as string | undefined}
      />
    )
  }

  if (span.type === "router_decision" && p.decision) {
    return (
      <RouterDecisionPanel
        decision={p.decision as Record<string, unknown>}
        prompt={p.prompt as string | null}
      />
    )
  }

  if (span.type === "tool_result") {
    return (
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 text-amber-600">
          tool result — {String(p.tool ?? "")}
        </div>
        <div className="rounded bg-background border border-border/50 p-2.5 overflow-x-auto">
          <pre className="font-mono text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap break-all">
            {typeof p.result_preview === "string" ? p.result_preview : JSON.stringify(p, null, 2)}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <pre className="font-mono text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap break-all">
      {JSON.stringify(p, null, 2)}
    </pre>
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
}: {
  span: Span
  depth: number
  isLast: boolean
  runStart: string
  runDurationMs: number
  expanded: boolean
  onToggle: () => void
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

  const hasPayload = Object.keys(p).length > 0
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
          <SpanDetailPanel span={span} />
        </div>
      )}
    </div>
  )
}
