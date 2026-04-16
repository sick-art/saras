/**
 * EvalRunDetail — results viewer for a completed (or in-progress) eval run.
 *
 * Layout (redesigned):
 *   Summary banner: agent version, item count, pass rate, metric stat cards
 *   Left panel:  item list with colored score dot
 *   Main area:   turn cards with progressive score disclosure
 */

import { GoldenReplayComparison } from "@/components/evals/GoldenReplayComparison"
import { MetricStatCard } from "@/components/evals/MetricStatCard"
import { PassFailBadge } from "@/components/evals/PassFailBadge"
import { TurnCard } from "@/components/evals/TurnCard"
import { TopBar } from "@/components/layout/TopBar"
import { Progress } from "@/components/ui/progress"
import { api, streamEvalRun } from "@/lib/api"
import {
  formatMetricName,
  getScoreStatus,
  scoreTextClass,
} from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type { AgentRecord } from "@/types/agent"
import type {
  Dataset,
  EvalProgressEvent,
  EvalResult,
  EvalRun,
  EvalRunStatus,
  ItemResults,
} from "@/types/eval"
import {
  ChevronLeft,
  Columns2,
  FlaskConical,
  Loader2,
  MessageSquare,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"

// ── Status badge ──────────────────────────────────────────────────────────────

function RunStatusBadge({ status }: { status: EvalRunStatus }) {
  const cfg: Record<EvalRunStatus, { label: string; className: string }> = {
    pending: { label: "Pending", className: "bg-muted text-muted-foreground" },
    running: { label: "Running", className: "bg-blue-500/10 text-blue-600" },
    completed: { label: "Complete", className: "bg-emerald-500/10 text-emerald-600" },
    failed: { label: "Failed", className: "bg-red-500/10 text-red-600" },
  }
  const { label, className } = cfg[status] ?? cfg.pending
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${className}`}
    >
      {label}
    </span>
  )
}

// ── Conversation-level scores ─────────────────────────────────────────────────

function ConversationScores({ scores }: { scores: EvalResult[] }) {
  if (scores.length === 0) return null

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Conversation-level Scores
      </p>
      <div className="space-y-3">
        {scores.map(s => {
          const info = getScoreStatus(s.score ?? 0)
          return (
            <div key={s.id} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{formatMetricName(s.metric_id)}</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-sm font-semibold tabular-nums", info.textClass)}>
                    {s.score !== null ? s.score.toFixed(2) : "—"}
                  </span>
                  <PassFailBadge score={s.score ?? 0} />
                </div>
              </div>
              {s.reasoning && (
                <p className="text-xs text-muted-foreground leading-relaxed pl-0.5">
                  {s.reasoning}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Conversation thread (turn cards) ──────────────────────────────────────────

function ConversationThread({ item }: { item: ItemResults }) {
  const turns = item.conversation?.turns ?? []
  const perTurnScores = item.scores.filter(
    s => s.scope === "per_turn" || s.scope === "tool_call",
  )
  const wholeConvScores = item.scores.filter(s => s.scope === "whole_conversation")

  if (turns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FlaskConical className="size-8 text-muted-foreground/30 mb-2" />
        <p className="text-sm text-muted-foreground">No conversation data</p>
      </div>
    )
  }

  return (
    <div className="space-y-3 py-4">
      {wholeConvScores.length > 0 && <ConversationScores scores={wholeConvScores} />}
      {turns.map(turn => {
        const turnScores = perTurnScores.filter(s => s.turn_index === turn.turn_index)
        return <TurnCard key={turn.turn_index} turn={turn} scores={turnScores} />
      })}
    </div>
  )
}

// ── EvalRunDetail ─────────────────────────────────────────────────────────────

export function EvalRunDetail() {
  const { projectId = "", runId = "" } = useParams<{ projectId: string; runId: string }>()

  const [run, setRun] = useState<EvalRun | null>(null)
  const [items, setItems] = useState<ItemResults[]>([])
  const [agent, setAgent] = useState<AgentRecord | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [progress, setProgress] = useState({ completed: 0, total: 0 })
  const [showComparison, setShowComparison] = useState(false)
  const stopStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (!projectId || !runId) return

    Promise.all([
      api.get<EvalRun>(`/projects/${projectId}/evals/runs/${runId}`),
      api.get<ItemResults[]>(`/projects/${projectId}/evals/runs/${runId}/items`),
    ]).then(([r, it]) => {
      setRun(r)
      setItems(it)
      if (it.length > 0) setSelectedItemId(it[0].dataset_item_id)
      setProgress({ completed: it.length, total: r.summary?.total_items ?? it.length })

      // Fetch agent and dataset for display names
      if (r.agent_id) {
        api.get<AgentRecord>(`/projects/${projectId}/agents/${r.agent_id}`)
          .then(setAgent)
          .catch(() => { /* ignore */ })
      }
      if (r.dataset_id) {
        api.get<Dataset>(`/projects/${projectId}/datasets/${r.dataset_id}`)
          .then(setDataset)
          .catch(() => { /* ignore */ })
      }
    }).finally(() => setLoading(false))
  }, [projectId, runId])

  // Stream progress for running evals
  useEffect(() => {
    if (!run || run.status !== "running") return

    const stop = streamEvalRun(projectId, runId, (event: EvalProgressEvent) => {
      if (event.type === "progress") {
        setProgress({ completed: event.completed, total: event.total })
      } else if (event.type === "item_done") {
        setProgress({ completed: event.completed, total: event.total })
        api
          .get<ItemResults[]>(`/projects/${projectId}/evals/runs/${runId}/items`)
          .then(it => {
            setItems(it)
            setSelectedItemId(prev => prev ?? (it.length > 0 ? it[0].dataset_item_id : null))
          })
      } else if (event.type === "complete") {
        api.get<EvalRun>(`/projects/${projectId}/evals/runs/${runId}`).then(setRun)
      }
    })

    stopStreamRef.current = stop
    return () => stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status, projectId, runId])

  const selectedItem = items.find(i => i.dataset_item_id === selectedItemId) ?? null

  // Summary stats
  const metricEntries = run?.summary?.metrics ? Object.entries(run.summary.metrics) : []
  const totalPassRate = metricEntries.length
    ? metricEntries.reduce((s, [, m]) => s + m.pass_rate, 0) / metricEntries.length
    : null

  if (loading) {
    return (
      <>
        <TopBar title="Eval Run" />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </main>
      </>
    )
  }

  if (!run) return null

  return (
    <>
      <TopBar
        title={
          <div className="flex items-center gap-2">
            <span className="font-semibold">Eval Run</span>
            <RunStatusBadge status={run.status} />
          </div>
        }
        breadcrumb={
          <Link
            to={`/projects/${projectId}/evals`}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors text-sm shrink-0"
          >
            <ChevronLeft className="size-4" />
            Evaluations
          </Link>
        }
      />

      <main className="flex-1 overflow-hidden flex flex-col">
        {/* ── Summary banner ────────────────────────────────────────────── */}
        <div className="border-b px-6 py-4 shrink-0 bg-muted/10 space-y-4">
          {/* Stats row */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {(agent || run.agent_version) && (
              <div className="flex flex-col">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Agent
                </span>
                <span className="font-medium">
                  {agent?.name ?? "Unknown"}
                  {run.agent_version && (
                    <span className="text-muted-foreground font-normal ml-1.5">
                      v{run.agent_version}
                    </span>
                  )}
                </span>
              </div>
            )}
            {dataset && (
              <div className="flex flex-col">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Dataset
                </span>
                <span className="font-medium">
                  {dataset.name}
                  <span className="text-muted-foreground font-normal ml-1.5 tabular-nums">
                    {items.length} {items.length === 1 ? "test case" : "test cases"}
                  </span>
                </span>
              </div>
            )}
            {totalPassRate !== null && (
              <div className="flex flex-col">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Pass Rate
                </span>
                <span className={cn("font-semibold", scoreTextClass(totalPassRate))}>
                  {Math.round(totalPassRate * 100)}%
                </span>
              </div>
            )}
            {run.summary?.total_items && (
              <span className="text-muted-foreground text-xs ml-auto tabular-nums self-end">
                {progress.completed}/{progress.total} scored
              </span>
            )}
          </div>

          {/* Metric stat cards */}
          {metricEntries.length > 0 && (
            <div className="flex flex-wrap gap-3">
              {metricEntries.map(([name, m]) => (
                <MetricStatCard key={name} metricId={name} avgScore={m.avg_score} />
              ))}
            </div>
          )}
        </div>

        {/* Progress bar (shown while running) */}
        {run.status === "running" && progress.total > 0 && (
          <Progress
            value={(progress.completed / progress.total) * 100}
            className="h-1 rounded-none"
          />
        )}

        {/* ── Body ──────────────────────────────────────────────────────── */}
        {items.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center">
            {run.status === "running" ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-5 animate-spin" />
                <span className="text-sm">Running evaluation…</span>
              </div>
            ) : (
              <div className="text-center">
                <FlaskConical className="size-10 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No results yet</p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-hidden flex">
            {/* Item list (left panel) */}
            <div className="w-48 shrink-0 border-r overflow-y-auto">
              
              <div className="p-2 space-y-1">
                {items.map((item, idx) => {
                  const scores = item.scores.map(r => r.score ?? 0)
                  // Item status = worst metric (any FAIL/WARN propagates up)
                  const worst = scores.length ? Math.min(...scores) : null
                  const failCount = scores.filter(s => s < 0.5).length
                  const warnCount = scores.filter(s => s >= 0.5 && s < 0.8).length
                  const isSelected = selectedItemId === item.dataset_item_id
                  const info = worst !== null ? getScoreStatus(worst) : null

                  return (
                    <button
                      key={item.dataset_item_id}
                      onClick={() => setSelectedItemId(item.dataset_item_id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 rounded-md text-left transition-colors text-xs",
                        isSelected
                          ? "bg-primary/10 text-primary font-medium"
                          : "hover:bg-muted/60 text-muted-foreground hover:text-foreground",
                      )}
                      title={
                        info
                          ? `${failCount} failed, ${warnCount} warning, ${scores.length - failCount - warnCount} passed`
                          : undefined
                      }
                    >
                      <span className={cn("size-2 rounded-full shrink-0", info?.dotClass ?? "bg-muted")} />
                      <span>Test case {idx + 1}</span>
                      {info && (
                        <span
                          className={cn(
                            "ml-auto text-[10px] font-semibold",
                            info.textClass,
                          )}
                        >
                          {info.label}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Main content */}
            {selectedItem ? (
              <div className="flex-1 overflow-hidden flex flex-col">
                {/* View toggle */}
                <div className="flex items-center gap-1 px-4 py-1.5 border-b bg-muted/20 shrink-0">
                  <button
                    className={cn(
                      "flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors",
                      !showComparison
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => setShowComparison(false)}
                  >
                    <MessageSquare className="size-3" />
                    Conversation
                  </button>
                  <button
                    className={cn(
                      "flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors",
                      showComparison
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => setShowComparison(true)}
                  >
                    <Columns2 className="size-3" />
                    Golden comparison
                  </button>
                </div>

                {/* Content area */}
                <div className="flex-1 overflow-y-auto px-6">
                  {showComparison ? (
                    <GoldenReplayComparison item={selectedItem} />
                  ) : (
                    <ConversationThread item={selectedItem} />
                  )}
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Select an item to view results</p>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  )
}
