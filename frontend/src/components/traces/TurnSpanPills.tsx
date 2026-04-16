/**
 * TurnSpanPills — horizontal strip of clickable pills representing the spans
 * emitted during one agent turn. Shared between the live simulator and the
 * recorded traces Chat view so the debug experience is identical in both.
 *
 * Pairs related spans (llm_call_start + llm_call_end, tool_call + tool_result)
 * so each logical operation is a single pill, opening a unified detail dialog.
 */

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { Span } from "@/types/trace"
import { fmt_ms, getSpanConfig, SpanDetailPanel } from "./SpanWaterfall"

// Spans that are pure timing beacons and add no information once their partner
// span (the matching "_decision" / "_end" / "_result") has the real payload.
const HIDDEN_SPAN_TYPES = new Set([
  "router_start",
  "turn_complete",
  "llm_call_start", // merged into llm_call_end
  "tool_call",      // merged into tool_result / tool_error
])

function pillLabel(span: Span, allSpans: Span[]): string {
  const p = span.payload ?? {}
  switch (span.type) {
    case "router_decision":
      return "Router"
    case "router_parse_error":
      return "Router error"
    case "llm_call_end": {
      // Iteration is 0-indexed; show as 1-indexed for users
      const iter = typeof p.iteration === "number" ? p.iteration + 1 : null
      const model = typeof p.model === "string" ? p.model : null
      const totalLLMs = allSpans.filter(s => s.type === "llm_call_end").length
      // Only show #N when there are multiple LLM calls in the turn
      const numSuffix = iter != null && totalLLMs > 1 ? ` #${iter}` : ""
      return model ? `LLM${numSuffix} (${model})` : `LLM${numSuffix}`
    }
    case "llm_call_start": {
      // Fallback while end span hasn't arrived yet (live streaming)
      const iter = typeof p.iteration === "number" ? p.iteration + 1 : null
      return iter != null ? `LLM #${iter} (running…)` : "LLM (running…)"
    }
    case "tool_result":
    case "tool_error":
      return `${String(p.tool ?? "tool")}${span.type === "tool_error" ? " (error)" : ""}`
    case "tool_call":
      return `${String(p.tool ?? "tool")} (running…)`
    case "tool_loop_exceeded":
      return "Tool loop exceeded"
    case "slot_fill":
      return `Slot: ${String(p.slot_name ?? "?")}`
    case "interrupt_triggered":
      return `Interrupt: ${String(p.trigger ?? "?")}`
    case "handoff_triggered":
      return `Handoff: ${String(p.target ?? "?")}`
    default:
      return getSpanConfig(span.type).label
  }
}

/** Pick the display span: prefer the "end" of a paired span if its partner is hidden */
function visibleSpansFor(spans: Span[]): Span[] {
  // Filter out hidden types BUT promote orphan starts (when end hasn't arrived yet) back
  const byIteration = new Map<number, Span>()
  for (const s of spans) {
    if (s.type === "llm_call_end" && typeof s.payload?.iteration === "number") {
      byIteration.set(s.payload.iteration, s)
    }
  }

  const toolResultParents = new Set<string>()
  for (const s of spans) {
    if ((s.type === "tool_result" || s.type === "tool_error") && s.parent_span_id) {
      toolResultParents.add(s.parent_span_id)
    }
  }

  return spans.filter(s => {
    if (s.type === "llm_call_end") return true
    if (s.type === "llm_call_start") {
      // Show the start span only if its end hasn't arrived
      const iter = s.payload?.iteration
      return typeof iter !== "number" || !byIteration.has(iter)
    }
    if (s.type === "tool_result" || s.type === "tool_error") return true
    if (s.type === "tool_call") {
      // Show the call span only if its result hasn't arrived
      return !toolResultParents.has(s.id)
    }
    return !HIDDEN_SPAN_TYPES.has(s.type)
  })
}

export function TurnSpanPills({ spans }: { spans: Span[] }) {
  const [active, setActive] = useState<Span | null>(null)

  const visible = visibleSpansFor(spans)
  if (visible.length === 0) return null

  return (
    <>
      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        {visible.map(span => {
          const cfg = getSpanConfig(span.type)
          const label = pillLabel(span, spans)
          const dur = span.duration_ms != null ? fmt_ms(span.duration_ms) : null
          return (
            <button
              key={span.id}
              type="button"
              onClick={() => setActive(span)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] font-medium leading-none",
                "transition-colors hover:brightness-110 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                cfg.pillColor,
              )}
              title={label}
            >
              <span>{label}</span>
              {dur && (
                <span className="opacity-60 tabular-nums font-normal">{dur}</span>
              )}
            </button>
          )
        })}
      </div>

      <Dialog open={active !== null} onOpenChange={(open) => { if (!open) setActive(null) }}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {active ? pillLabel(active, spans) : ""}
            </DialogTitle>
          </DialogHeader>
          {active && <SpanDetailPanel span={active} allSpans={spans} />}
        </DialogContent>
      </Dialog>
    </>
  )
}
