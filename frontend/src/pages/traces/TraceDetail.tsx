/**
 * TraceDetail — span waterfall for a single run.
 *
 * Route: /projects/:projectId/traces/:runId  (inside AppShell)
 */

import { TopBar } from "@/components/layout/TopBar"
import { Skeleton } from "@/components/ui/skeleton"
import {
  buildDepthMap,
  fmt_cost,
  fmt_ms,
  SpanRow,
  ToolChips,
  toolCountsFromSpans,
} from "@/components/traces/SpanWaterfall"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { RunDetail, RunStatus } from "@/types/trace"
import {
  AlertCircle,
  ChevronLeft,
  Clock,
  Coins,
  GitBranch,
  Hash,
  Layers,
  Wrench,
} from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

// ── Local helpers ──────────────────────────────────────────────────────────────

function fmt_duration(started: string, ended: string | null): string {
  if (!ended) return "—"
  return fmt_ms(new Date(ended).getTime() - new Date(started).getTime())
}

// ── Status badge ───────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: RunStatus }) {
  const color =
    status === "completed" ? "bg-emerald-500" :
    status === "failed"    ? "bg-red-500" :
    status === "cancelled" ? "bg-muted-foreground" :
                             "bg-blue-500 animate-pulse"
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium capitalize text-muted-foreground">
      <span className={cn("size-1.5 rounded-full shrink-0", color)} />
      {status}
    </span>
  )
}

// ── Stat chip ──────────────────────────────────────────────────────────────────

function StatChip({
  icon: Icon,
  value,
  label,
  className,
}: {
  icon: React.ElementType
  value: string
  label?: string
  className?: string
}) {
  return (
    <div className={cn("flex items-center gap-1.5 text-sm", className)}>
      <Icon className="size-3.5 text-muted-foreground shrink-0" />
      <span className="tabular-nums font-medium">{value}</span>
      {label && <span className="text-muted-foreground text-xs">{label}</span>}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export function TraceDetail() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>()

  const [run, setRun]           = useState<RunDetail | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!projectId || !runId) return
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const data = await api.get<RunDetail>(`/projects/${projectId}/runs/${runId}`)
        if (!cancelled) { setRun(data); setLoading(false) }
      } catch (e) {
        if (!cancelled) { setError((e as Error).message); setLoading(false) }
      }
    }
    load()
    return () => { cancelled = true }
  }, [projectId, runId])

  const toggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const runDurationMs = run?.ended_at
    ? new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()
    : 0

  const depths = run ? buildDepthMap(run.spans) : new Map<string, number>()

  const sortedSpans = run
    ? [...run.spans].sort((a, b) =>
        new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
      )
    : []

  const breadcrumb = (
    <div className="flex items-center gap-2 text-sm min-w-0">
      <Link
        to={`/projects/${projectId}/traces`}
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
      >
        <ChevronLeft className="size-3.5" />
        Traces
      </Link>
      {run && (
        <>
          <span className="text-border">/</span>
          <span className="font-semibold truncate max-w-[300px]">
            {run.agent_name ?? "Unknown agent"}
          </span>
        </>
      )}
    </div>
  )

  return (
    <>
      <TopBar title={breadcrumb} />

      <main className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-6 space-y-3">
            <Skeleton className="h-16 w-full rounded-lg" />
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full rounded" />
            ))}
          </div>
        ) : error ? (
          <div className="p-6">
            <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              <AlertCircle className="size-4 shrink-0" />
              {error}
            </div>
          </div>
        ) : !run ? null : (
          <>
            {/* ── Run header ───────────────────────────────────────────────── */}
            <div className="border-b bg-muted/20 px-6 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <StatusDot status={run.status} />

                <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium text-muted-foreground capitalize">
                  {run.source}
                </span>

                <div className="w-px h-4 bg-border" />

                <StatChip icon={Clock} value={fmt_duration(run.started_at, run.ended_at)} />
                <StatChip icon={Hash} value={run.total_tokens.toLocaleString()} label="tokens" />
                <StatChip icon={Coins} value={fmt_cost(run.total_cost_usd) || "$0"} />
                <StatChip icon={Layers} value={String(run.spans.length)} label="spans" />

                <div className="ml-auto flex items-center gap-4 text-xs text-muted-foreground/50">
                  <span className="font-mono">{run.id}</span>
                </div>
              </div>

              <div className="mt-1.5 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
                <span>Started {new Date(run.started_at).toLocaleString()}</span>
                {run.ended_at && <span>Ended {new Date(run.ended_at).toLocaleString()}</span>}
                {run.session_id && <span>Session {run.session_id}</span>}
              </div>
              {(() => {
                const toolCounts = toolCountsFromSpans(run.spans)
                return Object.keys(toolCounts).length > 0 ? (
                  <div className="mt-2 flex items-center gap-2">
                    <Wrench className="size-3 text-muted-foreground/50 shrink-0" />
                    <ToolChips toolCounts={toolCounts} />
                  </div>
                ) : null
              })()}
            </div>

            {/* ── Waterfall table ───────────────────────────────────────────── */}
            <div className="px-4 pt-3 pb-1 flex items-center gap-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 select-none">
              <div className="w-[calc(280px+var(--depth,0px)+64px)] shrink-0">Span</div>
              <div className="flex-1 px-4">Timeline</div>
              <div className="w-56 pr-2 text-right">Duration · Tokens · Cost</div>
            </div>

            <div className="px-4 pb-6">
              {sortedSpans.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-14 text-center mt-2">
                  <GitBranch className="size-8 text-muted-foreground/25 mb-2" />
                  <p className="text-sm text-muted-foreground">No spans recorded for this run.</p>
                </div>
              ) : (
                <div className="rounded-lg border bg-card overflow-hidden">
                  {sortedSpans.map((span, i) => (
                    <div
                      key={span.id}
                      className={cn(i < sortedSpans.length - 1 && "border-b border-border/40")}
                    >
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
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </>
  )
}
