/**
 * EvalSuiteDetail — configure metrics and trigger eval runs.
 *
 * Layout:
 *   Top: suite name + agent/dataset selectors + "Run Eval" button
 *   Left: Metric picker grouped by type (LLM Judge / Deterministic) + collapsible YAML editor
 *   Right: Run history with PASS/FAIL indicators
 */

import { useEffect, useState, lazy, Suspense } from "react"
import { Link, useParams, useNavigate } from "react-router-dom"
import {
  ChevronLeft,
  Play,
  Loader2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Square,
  CheckSquare,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { PassFailBadge } from "@/components/evals/PassFailBadge"
import { scoreTextClass } from "@/lib/score-utils"
import type { EvalSuite, EvalRun, EvalRunStatus, PresetMetric, Dataset } from "@/types/eval"
import type { AgentRecord } from "@/types/agent"

const MonacoEditor = lazy(() =>
  import("@monaco-editor/react").then(m => ({ default: m.default })),
)

// ── Helpers ───────────────────────────────────────────────────────────────────

/** ULID pattern: 26 uppercase alphanumeric chars */
const ULID_RE = /^[0-9A-Z]{26}$/

/** Display name for entities — truncates if name looks like a ULID */
function displayName(name: string, fallback?: string): string {
  if (!name) return fallback ?? "Unnamed"
  if (ULID_RE.test(name)) return `${name.slice(0, 8)}…`
  return name
}

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

// ── Scope badge ───────────────────────────────────────────────────────────────

function ScopeBadge({ scope }: { scope: string }) {
  const labels: Record<string, string> = {
    per_turn: "Per turn",
    whole_conversation: "Full conv.",
    tool_call: "Tool call",
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">
      {labels[scope] ?? scope}
    </span>
  )
}

// ── Compact metric row (checkbox-style) ───────────────────────────────────────

function MetricRow({
  preset,
  selected,
  onToggle,
}: {
  preset: PresetMetric
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "w-full flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors",
        selected
          ? "bg-primary/5 hover:bg-primary/10"
          : "hover:bg-muted/40",
      )}
    >
      {selected ? (
        <CheckSquare className="size-4 text-primary shrink-0" />
      ) : (
        <Square className="size-4 text-muted-foreground/50 shrink-0" />
      )}
      <span className={cn("text-xs font-medium flex-1 min-w-0 truncate", selected && "text-primary")}>
        {preset.name}
      </span>
      <ScopeBadge scope={preset.scope} />
    </button>
  )
}

// ── EvalSuiteDetail ───────────────────────────────────────────────────────────

export function EvalSuiteDetail() {
  const { projectId = "", suiteId = "" } = useParams<{ projectId: string; suiteId: string }>()
  const navigate = useNavigate()

  const [suite, setSuite] = useState<EvalSuite | null>(null)
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [presets, setPresets] = useState<PresetMetric[]>([])
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)

  // Selection for triggering a run
  const [selectedAgentId, setSelectedAgentId] = useState("")
  const [selectedDatasetId, setSelectedDatasetId] = useState("")
  const [triggering, setTriggering] = useState(false)

  // Metric YAML editing
  const [yaml, setYaml] = useState("")
  const [saving, setSaving] = useState(false)
  const [showYaml, setShowYaml] = useState(false)

  // Selected preset keys (derived from yaml on load; mutated via picker)
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!projectId || !suiteId) return
    Promise.all([
      api.get<EvalSuite>(`/projects/${projectId}/evals/suites/${suiteId}`),
      api.get<EvalRun[]>(`/projects/${projectId}/evals/runs?suite_id=${suiteId}`),
      api.get<PresetMetric[]>(`/projects/${projectId}/evals/presets`),
      api.get<AgentRecord[]>(`/projects/${projectId}/agents`),
      api.get<Dataset[]>(`/projects/${projectId}/datasets`),
    ])
      .then(([s, r, p, a, d]) => {
        setSuite(s)
        setRuns(r)
        setPresets(p)
        setAgents(a)
        setDatasets(d)
        setYaml(s.metric_set_yaml)
        // Parse selected presets from yaml
        try {
          const lines = s.metric_set_yaml.split("\n")
          const keys = new Set(
            lines
              .map(l => l.match(/^\s*-\s*preset:\s*(\S+)/)?.[1])
              .filter(Boolean) as string[],
          )
          setSelectedPresets(keys)
        } catch {
          /* ignore */
        }
        // Pre-select first agent/dataset
        if (a.length > 0) setSelectedAgentId(a[0].id)
        if (d.length > 0) setSelectedDatasetId(d[0].id)
      })
      .finally(() => setLoading(false))
  }, [projectId, suiteId])

  const togglePreset = (key: string) => {
    setSelectedPresets(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      // Regenerate YAML from selection
      const lines = ["metrics:"]
      for (const k of next) lines.push(`  - preset: ${k}`)
      setYaml(lines.join("\n") + "\n")
      return next
    })
  }

  const saveYaml = async () => {
    setSaving(true)
    try {
      await api.patch<EvalSuite>(`/projects/${projectId}/evals/suites/${suiteId}`, {
        metric_set_yaml: yaml,
      })
    } finally {
      setSaving(false)
    }
  }

  const triggerRun = async () => {
    if (!selectedAgentId || !selectedDatasetId) return
    setTriggering(true)
    try {
      // Save current yaml first
      await api.patch<EvalSuite>(`/projects/${projectId}/evals/suites/${suiteId}`, {
        metric_set_yaml: yaml,
      })
      const run = await api.post<EvalRun>(
        `/projects/${projectId}/evals/suites/${suiteId}/runs`,
        { dataset_id: selectedDatasetId, agent_id: selectedAgentId },
      )
      navigate(`/projects/${projectId}/evals/runs/${run.id}`)
    } finally {
      setTriggering(false)
    }
  }

  if (loading) {
    return (
      <>
        <TopBar title="Eval Suite" />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </main>
      </>
    )
  }

  if (!suite) return null

  // Group presets by type
  const llmJudgePresets = presets.filter(p => p.type === "llm_judge")
  const deterministicPresets = presets.filter(p => p.type === "deterministic")

  return (
    <>
      <TopBar
        title={suite.name}
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
      <main className="flex-1 overflow-y-auto p-6">
        {/* Run trigger bar */}
        <div className="flex flex-wrap items-end gap-3 mb-8 p-4 rounded-lg border bg-muted/30">
          <div className="space-y-1 min-w-[180px]">
            <Label className="text-xs">Agent</Label>
            <Select value={selectedAgentId} onValueChange={v => setSelectedAgentId(v ?? "")}>
              <SelectTrigger className="h-8 text-sm">
                <SelectValue placeholder="Select agent…">
                  {selectedAgentId
                    ? displayName(
                        agents.find(a => a.id === selectedAgentId)?.name ?? "",
                        selectedAgentId.slice(0, 8),
                      )
                    : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {agents.map(a => (
                  <SelectItem key={a.id} value={a.id}>
                    {displayName(a.name, a.id.slice(0, 8))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 min-w-[180px]">
            <Label className="text-xs">Dataset</Label>
            <Select
              value={selectedDatasetId}
              onValueChange={v => setSelectedDatasetId(v ?? "")}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue placeholder="Select dataset…">
                  {selectedDatasetId
                    ? displayName(
                        datasets.find(d => d.id === selectedDatasetId)?.name ?? "",
                        selectedDatasetId.slice(0, 8),
                      )
                    : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {datasets.map(d => (
                  <SelectItem key={d.id} value={d.id}>
                    {displayName(d.name, d.id.slice(0, 8))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={triggerRun}
            disabled={!selectedAgentId || !selectedDatasetId || triggering}
            className="ml-auto"
          >
            {triggering ? (
              <Loader2 className="size-4 mr-2 animate-spin" />
            ) : (
              <Play className="size-4 mr-2" />
            )}
            Run eval
          </Button>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* ── Metric picker ────────────────────────────────────────────── */}
          <div className="lg:w-[30%] shrink-0">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-medium text-sm">Metrics</h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {selectedPresets.size} selected
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={saveYaml}
                  disabled={saving}
                >
                  {saving && <Loader2 className="size-3 animate-spin" />}
                  Save
                </Button>
              </div>
            </div>

            {/* LLM Judge group */}
            {llmJudgePresets.length > 0 && (
              <div className="mb-4">
                <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide px-2.5 mb-1.5">
                  LLM Judge
                </p>
                <div className="space-y-0.5">
                  {llmJudgePresets.map(p => (
                    <MetricRow
                      key={p.key}
                      preset={p}
                      selected={selectedPresets.has(p.key)}
                      onToggle={() => togglePreset(p.key)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Deterministic group */}
            {deterministicPresets.length > 0 && (
              <div className="mb-4">
                <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide px-2.5 mb-1.5">
                  Deterministic
                </p>
                <div className="space-y-0.5">
                  {deterministicPresets.map(p => (
                    <MetricRow
                      key={p.key}
                      preset={p}
                      selected={selectedPresets.has(p.key)}
                      onToggle={() => togglePreset(p.key)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Collapsible YAML editor */}
            <div className="border rounded-lg overflow-hidden">
              <button
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
                onClick={() => setShowYaml(v => !v)}
              >
                <span>Advanced: edit metric YAML</span>
                {showYaml ? (
                  <ChevronDown className="size-3.5" />
                ) : (
                  <ChevronRight className="size-3.5" />
                )}
              </button>
              {showYaml && (
                <Suspense
                  fallback={
                    <div className="h-48 flex items-center justify-center">
                      <Loader2 className="size-4 animate-spin" />
                    </div>
                  }
                >
                  <MonacoEditor
                    height="240px"
                    language="yaml"
                    value={yaml}
                    onChange={v => setYaml(v ?? "")}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 12,
                      lineNumbers: "off",
                      scrollBeyondLastLine: false,
                      padding: { top: 8, bottom: 8 },
                    }}
                  />
                </Suspense>
              )}
            </div>
          </div>

          {/* ── Run history ──────────────────────────────────────────────── */}
          <div className="flex-1 min-w-0">
            <h3 className="font-medium text-sm mb-3">Run history</h3>
            {runs.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-10 text-center">
                <FlaskConical className="size-8 text-muted-foreground/30 mb-2" />
                <p className="text-sm text-muted-foreground">No runs yet</p>
              </div>
            ) : (
              <div className="space-y-2">
                {runs.map(run => {
                  const passRate = run.summary?.metrics
                    ? Object.values(run.summary.metrics).reduce((s, m) => s + m.pass_rate, 0) /
                      Object.keys(run.summary.metrics).length
                    : null

                  return (
                    <Link
                      key={run.id}
                      to={`/projects/${projectId}/evals/runs/${run.id}`}
                      className="flex items-center justify-between p-3 rounded-lg border hover:border-primary/50 hover:bg-muted/30 transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <RunStatusBadge status={run.status} />
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">
                            {run.agent_version ? `v${run.agent_version}` : "—"}
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            {run.started_at
                              ? new Date(run.started_at).toLocaleString()
                              : "Pending"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {passRate !== null && (
                          <div className="flex items-center gap-1.5">
                            <span
                              className={cn(
                                "text-xs font-semibold tabular-nums",
                                scoreTextClass(passRate),
                              )}
                            >
                              {Math.round(passRate * 100)}%
                            </span>
                            <PassFailBadge score={passRate} />
                          </div>
                        )}
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {run.result_count} results
                        </span>
                        <ChevronRight className="size-3.5 text-muted-foreground" />
                      </div>
                    </Link>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  )
}
