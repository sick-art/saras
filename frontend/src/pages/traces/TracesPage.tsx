/**
 * TracesPage — Sessions list (default) and Runs list.
 *
 * Sessions tab: groups of runs by session_id, click → SessionDetail
 * Runs tab:     flat run list with filters, click → TraceDetail
 */

import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  AlertCircle,
  ChevronRight,
  GitBranch,
  RefreshCw,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type {
  RunListResponse, RunSource, RunStatus, RunSummary,
  SessionListResponse, SessionSummary,
} from "@/types/trace"

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDuration(started: string, ended: string | null): string {
  if (!ended) return "—"
  const ms = new Date(ended).getTime() - new Date(started).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000)      return "just now"
  if (ms < 3_600_000)   return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000)  return `${Math.floor(ms / 3_600_000)}h ago`
  return new Date(iso).toLocaleDateString()
}

function formatCost(usd: number): string {
  if (usd === 0)    return "$0"
  if (usd < 0.001)  return "<$0.001"
  return `$${usd.toFixed(4)}`
}

function formatTokens(n: number): string {
  if (n === 0)          return "0"
  if (n >= 1_000_000)   return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)       return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

// ── Layout constants ──────────────────────────────────────────────────────────

// Fixed-width column templates ensure header + every row align identically
// (each row is its own grid container, so `auto` columns end up ragged)
const SESSIONS_GRID = "grid grid-cols-[1fr_88px_64px_72px_72px_72px_20px] items-center gap-x-5 px-4"
const RUNS_GRID = "grid grid-cols-[1fr_88px_64px_72px_72px_64px_20px] items-center gap-x-5 px-4"

// ── Status / source styling ────────────────────────────────────────────────────

const STATUS_DOT: Record<RunStatus, string> = {
  running:   "bg-blue-500 animate-pulse",
  completed: "bg-emerald-500",
  failed:    "bg-red-500",
  cancelled: "bg-muted-foreground",
}

// Source pills use neutral styling — they're categorical, not semantic.
// Type/origin info shouldn't compete with status colors for attention.
const SOURCE_LABEL: Record<RunSource, string> = {
  simulator:  "Simulator",
  production: "Production",
  sdk:        "SDK",
}

// ── Session row ────────────────────────────────────────────────────────────────

function SessionRow({ session, projectId }: { session: SessionSummary; projectId: string }) {
  const shortId = session.session_id.slice(-8).toUpperCase()
  return (
    <Link
      to={`/projects/${projectId}/traces/sessions/${session.session_id}`}
      className={cn(
        "group py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors",
        SESSIONS_GRID,
      )}
    >
      {/* Agent + session id */}
      <div className="min-w-0">
        <p className="text-sm font-medium truncate leading-tight">
          {session.agent_name
            ? session.agent_name
            : <span className="text-muted-foreground italic text-xs">Unknown agent</span>
          }
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="flex items-center gap-1.5">
            <span className={cn("size-1.5 rounded-full shrink-0", STATUS_DOT[session.status] ?? "bg-muted")} />
            <span className="text-xs capitalize text-muted-foreground">
              {session.status}
            </span>
          </span>
          <span className="text-[10px] font-mono text-muted-foreground/50">{shortId}</span>
          {session.agent_version && (
            <span className="text-[10px] text-muted-foreground/50 font-mono">v{session.agent_version}</span>
          )}
        </div>
      </div>

      {/* Started */}
      <div className="text-xs text-muted-foreground tabular-nums text-right" title={session.started_at}>
        {formatRelative(session.started_at)}
      </div>

      {/* Duration */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatDuration(session.started_at, session.ended_at)}
      </div>

      {/* Runs */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {session.run_count} {session.run_count === 1 ? "run" : "runs"}
      </div>

      {/* Tokens */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatTokens(session.total_tokens)}
      </div>

      {/* Cost */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatCost(session.total_cost_usd)}
      </div>

      {/* Chevron */}
      <ChevronRight className="size-3.5 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors" />
    </Link>
  )
}

function SessionRowSkeleton() {
  return (
    <div className="flex items-center gap-5 px-4 py-3 border-b border-border/50 last:border-0">
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-36" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-3 w-12" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="size-3.5 rounded" />
    </div>
  )
}

// ── Sessions tab content ───────────────────────────────────────────────────────

function SessionsTab({ projectId }: { projectId: string }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [total, setTotal]       = useState(0)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [offset, setOffset]     = useState(0)

  const PAGE_SIZE = 50

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const p = new URLSearchParams()
      p.set("limit",  String(PAGE_SIZE))
      p.set("offset", String(offset))
      const data = await api.get<SessionListResponse>(`/projects/${projectId}/sessions?${p}`)
      setSessions(data.sessions)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sessions")
    } finally {
      setLoading(false)
    }
  }, [projectId, offset])

  useEffect(() => { load() }, [load])

  const totalPages  = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        <AlertCircle className="size-4 shrink-0" />
        {error}
      </div>
    )
  }

  return (
    <>
      <div className="rounded-lg border bg-card overflow-hidden">
        {!loading && sessions.length > 0 && (
          <div className={cn(
            "py-2 bg-muted/30 border-b border-border/50 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 select-none",
            SESSIONS_GRID,
          )}>
            <span>Agent</span>
            <span className="text-right">Started</span>
            <span className="text-right">Duration</span>
            <span className="text-right">Runs</span>
            <span className="text-right">Tokens</span>
            <span className="text-right">Cost</span>
            <span />
          </div>
        )}

        {loading ? (
          Array.from({ length: 8 }).map((_, i) => <SessionRowSkeleton key={i} />)
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <GitBranch className="size-9 text-muted-foreground/25 mb-3" />
            <p className="font-medium text-sm">No sessions found</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Run the simulator or connect your SDK to start capturing sessions.
            </p>
          </div>
        ) : (
          sessions.map(s => <SessionRow key={s.session_id} session={s} projectId={projectId} />)
        )}
      </div>

      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-muted-foreground">
          <span>{total.toLocaleString()} sessions</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <span className="px-2 text-xs">Page {currentPage} of {totalPages}</span>
            <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </>
  )
}

// ── Filter pill ────────────────────────────────────────────────────────────────

type StatusFilter = "all" | RunStatus
type SourceFilter = "all" | RunSource

function FilterPill({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-md px-2.5 py-1 text-xs font-medium transition-colors capitalize",
        active
          ? "bg-muted text-foreground"
          : "bg-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground"
      )}
    >
      {children}
    </button>
  )
}

// ── Run row ────────────────────────────────────────────────────────────────────

function RunRow({ run, projectId }: { run: RunSummary; projectId: string }) {
  return (
    <Link
      to={`/projects/${projectId}/traces/${run.id}`}
      className={cn(
        "group py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors",
        RUNS_GRID,
      )}
    >
      {/* Agent name + version */}
      <div className="min-w-0">
        <p className="text-sm font-medium truncate leading-tight">
          {run.agent_name
            ? run.agent_name
            : <span className="text-muted-foreground italic text-xs">Unknown agent</span>
          }
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          {/* Status */}
          <span className="flex items-center gap-1.5">
            <span className={cn("size-1.5 rounded-full shrink-0", STATUS_DOT[run.status] ?? "bg-muted")} />
            <span className="text-xs capitalize text-muted-foreground">
              {run.status}
            </span>
          </span>
          {/* Source pill (neutral) */}
          <span className="rounded px-1.5 py-0 text-[10px] font-medium leading-4 bg-muted text-muted-foreground">
            {SOURCE_LABEL[run.source] ?? run.source}
          </span>
          {/* Version */}
          {run.agent_version && (
            <span className="text-[10px] text-muted-foreground/50 font-mono">v{run.agent_version}</span>
          )}
        </div>
      </div>

      {/* Started */}
      <div className="text-xs text-muted-foreground tabular-nums text-right" title={run.started_at}>
        {formatRelative(run.started_at)}
      </div>

      {/* Duration */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatDuration(run.started_at, run.ended_at)}
      </div>

      {/* Tokens */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatTokens(run.total_tokens)}
      </div>

      {/* Cost */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {formatCost(run.total_cost_usd)}
      </div>

      {/* Span count */}
      <div className="text-xs text-muted-foreground tabular-nums text-right">
        {run.span_count ?? "—"}
      </div>

      {/* Chevron */}
      <ChevronRight className="size-3.5 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors" />
    </Link>
  )
}

// ── Skeleton row ───────────────────────────────────────────────────────────────

function RunRowSkeleton() {
  return (
    <div className="flex items-center gap-5 px-4 py-3 border-b border-border/50 last:border-0">
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-36" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-12" />
      <Skeleton className="h-3 w-10" />
      <Skeleton className="h-3 w-8" />
      <Skeleton className="size-3.5 rounded" />
    </div>
  )
}

// ── Runs tab content ───────────────────────────────────────────────────────────

const PAGE_SIZE = 50

function RunsTab({ projectId }: { projectId: string }) {
  const [runs, setRuns]     = useState<RunSummary[]>([])
  const [total, setTotal]   = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const p = new URLSearchParams()
      if (statusFilter !== "all") p.set("status", statusFilter)
      if (sourceFilter !== "all") p.set("source", sourceFilter)
      p.set("limit",  String(PAGE_SIZE))
      p.set("offset", String(offset))

      const data = await api.get<RunListResponse>(`/projects/${projectId}/runs?${p}`)
      setRuns(data.runs)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs")
    } finally {
      setLoading(false)
    }
  }, [projectId, statusFilter, sourceFilter, offset])

  useEffect(() => { setOffset(0) }, [statusFilter, sourceFilter])
  useEffect(() => { load() }, [load])

  const totalPages  = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <>
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-5 mb-5">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium w-10 shrink-0">Status</span>
          {(["all", "running", "completed", "failed"] as StatusFilter[]).map(s => (
            <FilterPill key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
              {s === "all" ? "All" : s}
            </FilterPill>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium w-10 shrink-0">Source</span>
          {(["all", "simulator", "production", "sdk"] as SourceFilter[]).map(s => (
            <FilterPill key={s} active={sourceFilter === s} onClick={() => setSourceFilter(s)}>
              {s === "all" ? "All" : s}
            </FilterPill>
          ))}
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertCircle className="size-4 shrink-0" />
          {error}
        </div>
      ) : (
        <div className="rounded-lg border bg-card overflow-hidden">
          {!loading && runs.length > 0 && (
            <div className={cn(
              "py-2 bg-muted/30 border-b border-border/50 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60 select-none",
              RUNS_GRID,
            )}>
              <span>Agent</span>
              <span className="text-right">Started</span>
              <span className="text-right">Duration</span>
              <span className="text-right">Tokens</span>
              <span className="text-right">Cost</span>
              <span className="text-right">Spans</span>
              <span />
            </div>
          )}

          {loading ? (
            Array.from({ length: 8 }).map((_, i) => <RunRowSkeleton key={i} />)
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <GitBranch className="size-9 text-muted-foreground/25 mb-3" />
              <p className="font-medium text-sm">No traces found</p>
              <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                {statusFilter !== "all" || sourceFilter !== "all"
                  ? "No runs match the current filters."
                  : "Run the simulator or connect your SDK to start capturing traces."}
              </p>
            </div>
          ) : (
            runs.map(run => <RunRow key={run.id} run={run} projectId={projectId} />)
          )}
        </div>
      )}

      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-muted-foreground">
          <span>{total.toLocaleString()} runs</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <span className="px-2 text-xs">Page {currentPage} of {totalPages}</span>
            <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export function TracesPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [activeTab, setActiveTab] = useState<"sessions" | "runs">("sessions")

  if (!projectId) return null

  return (
    <>
      <TopBar title="Traces" />
      <main className="flex-1 overflow-y-auto p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-xl font-semibold">Traces</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Browse conversation sessions and inspect individual runs.
            </p>
          </div>
          <Button
            variant="ghost" size="sm"
            onClick={() => {
              // Re-mount tabs by toggling — child components handle their own refresh
              setActiveTab(t => t)
            }}
            className="gap-1.5 text-muted-foreground"
          >
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>

        <Tabs value={activeTab} onValueChange={v => setActiveTab(v as "sessions" | "runs")}>
          <TabsList variant="line" className="mb-5">
            <TabsTrigger value="sessions">Sessions</TabsTrigger>
            <TabsTrigger value="runs">Runs</TabsTrigger>
          </TabsList>

          <TabsContent value="sessions">
            <SessionsTab projectId={projectId} />
          </TabsContent>

          <TabsContent value="runs">
            <RunsTab projectId={projectId} />
          </TabsContent>
        </Tabs>
      </main>
    </>
  )
}
