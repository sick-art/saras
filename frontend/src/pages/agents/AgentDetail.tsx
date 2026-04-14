/**
 * AgentDetail — /projects/:projectId/agents/:agentId
 *
 * Shows:
 * - Agent name, description, version, published status
 * - Validation badge (runs on load)
 * - Key stats from parsedSchema (conditions count, tools count, handoffs)
 * - Version history list
 * - Open Builder / Simulate action buttons
 */

import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import * as jsyaml from "js-yaml"
import {
  ChevronLeft,
  ExternalLink,
  Play,
  GitBranch,
  Wrench,
  ArrowRightLeft,
  Zap,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Loader2,
  History,
  Info,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { buttonVariants } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { AgentRecord, AgentVersionRecord } from "@/types/agent"

interface ValidationResult {
  valid: boolean
  errors: { message: string; path: string | null }[]
  warnings: { message: string; path: string | null }[]
  infos: { message: string; path: string | null }[]
}

// ── Stat tile ──────────────────────────────────────────────────────────────────

function StatTile({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: number | string
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
    </div>
  )
}

// ── Validation badge ───────────────────────────────────────────────────────────

function ValidationBadge({
  result,
  loading,
}: {
  result: ValidationResult | null
  loading: boolean
}) {
  if (loading) {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="animate-spin" data-icon="inline-start" />
        Validating…
      </Badge>
    )
  }
  if (!result) return null

  if (result.errors.length > 0) {
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle data-icon="inline-start" />
        {result.errors.length} error{result.errors.length > 1 ? "s" : ""}
      </Badge>
    )
  }
  if (result.warnings.length > 0) {
    return (
      <Badge variant="outline" className="gap-1 border-amber-500/50 text-amber-600">
        <AlertTriangle data-icon="inline-start" />
        {result.warnings.length} warning{result.warnings.length > 1 ? "s" : ""}
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 border-emerald-500/50 text-emerald-600">
      <CheckCircle2 data-icon="inline-start" />
      Valid
    </Badge>
  )
}

// ── Version history row ────────────────────────────────────────────────────────

function VersionRow({
  version,
  isCurrent,
}: {
  version: AgentVersionRecord
  isCurrent: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-mono text-xs font-medium shrink-0">v{version.version}</span>
        {isCurrent && (
          <Badge variant="secondary" className="text-[10px] shrink-0">
            current
          </Badge>
        )}
        {version.change_summary && (
          <span className="text-xs text-muted-foreground truncate">{version.change_summary}</span>
        )}
      </div>
      <span className="text-xs text-muted-foreground shrink-0">
        {new Date(version.created_at).toLocaleDateString()}
      </span>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export function AgentDetail() {
  const { projectId, agentId } = useParams<{ projectId: string; agentId: string }>()

  const [agent, setAgent] = useState<AgentRecord | null>(null)
  const [versions, setVersions] = useState<AgentVersionRecord[]>([])
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || !agentId) return

    setLoading(true)
    Promise.all([
      api.get<AgentRecord>(`/projects/${projectId}/agents/${agentId}`),
      api.get<AgentVersionRecord[]>(`/projects/${projectId}/agents/${agentId}/versions`),
    ])
      .then(([agentData, versionData]) => {
        setAgent(agentData)
        setVersions(versionData)
        // Kick off validation immediately
        setValidating(true)
        return api.post<ValidationResult>(
          `/projects/${projectId}/agents/${agentId}/validate`,
          { yaml_content: agentData.yaml_content },
        )
      })
      .then(setValidation)
      .catch((e) => setError(e.message))
      .finally(() => {
        setLoading(false)
        setValidating(false)
      })
  }, [projectId, agentId])

  // Derive schema stats from YAML without importing js-yaml (just regex counts)
  const stats = agent ? deriveStats(agent.yaml_content) : null

  if (loading) {
    return (
      <>
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6 max-w-4xl mx-auto">
          <Skeleton className="h-6 w-48 mb-6" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)}
          </div>
          <Skeleton className="h-40" />
        </main>
      </>
    )
  }

  if (error || !agent) {
    return (
      <>
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="flex items-center gap-2 text-destructive text-sm">
            <AlertCircle className="size-4" />
            {error ?? "Agent not found"}
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <TopBar />
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">

          {/* Breadcrumb + actions */}
          <div className="flex items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-2 min-w-0">
              <Link
                to={`/projects/${projectId}/agents`}
                className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
              >
                <ChevronLeft className="size-4" />
              </Link>
              <h1 className="text-xl font-semibold truncate">{agent.name}</h1>
              <span className="text-sm text-muted-foreground shrink-0">
                v{agent.current_version}
              </span>
              {agent.is_published && (
                <Badge variant="secondary" className="shrink-0">Published</Badge>
              )}
              <ValidationBadge result={validation} loading={validating} />
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Link
                to={`/projects/${projectId}/agents/${agentId}/builder`}
                className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
              >
                <ExternalLink data-icon="inline-start" />
                Open Builder
              </Link>
              <Link
                to={`/projects/${projectId}/agents/${agentId}/simulate`}
                className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
              >
                <Play data-icon="inline-start" />
                Simulate
              </Link>
            </div>
          </div>

          {/* Description */}
          {agent.description && (
            <p className="text-sm text-muted-foreground mb-6 max-w-2xl">{agent.description}</p>
          )}

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              <StatTile icon={GitBranch} label="Conditions" value={stats.conditions} />
              <StatTile icon={Wrench} label="Tools" value={stats.tools} />
              <StatTile icon={ArrowRightLeft} label="Handoffs" value={stats.handoffs} />
              <StatTile icon={Zap} label="Interrupts" value={stats.interrupts} />
            </div>
          )}

          {/* Validation detail */}
          {validation && (validation.errors.length > 0 || validation.warnings.length > 0) && (
            <Card className="mb-6">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Info className="size-4 text-muted-foreground" />
                  Validation issues
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-1.5">
                  {[...validation.errors, ...validation.warnings].map((issue, i) => (
                    <div
                      key={i}
                      className={cn(
                        "flex items-start gap-2 text-xs",
                        issue.path === "error" ? "text-destructive" : "text-amber-600",
                      )}
                    >
                      {validation.errors.includes(issue as never) ? (
                        <AlertCircle className="size-3.5 mt-0.5 shrink-0" />
                      ) : (
                        <AlertTriangle className="size-3.5 mt-0.5 shrink-0" />
                      )}
                      <span>
                        {issue.path && (
                          <span className="font-mono text-muted-foreground mr-1">{issue.path}</span>
                        )}
                        {issue.message}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Version history */}
          {versions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <History className="size-4 text-muted-foreground" />
                  Version history
                </CardTitle>
                <CardDescription>{versions.length} version{versions.length > 1 ? "s" : ""}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col divide-y divide-border">
                  {versions.map((v) => (
                    <VersionRow
                      key={v.id}
                      version={v}
                      isCurrent={v.version === agent.current_version}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </>
  )
}

// ── Stats derivation via js-yaml ──────────────────────────────────────────────

function deriveStats(yamlContent: string) {
  try {
    const raw = jsyaml.load(yamlContent) as Record<string, unknown> | null
    const schema = (raw?.agent ?? {}) as Record<string, unknown[]>
    return {
      conditions: Array.isArray(schema.conditions) ? schema.conditions.length : 0,
      tools: Array.isArray(schema.tools) ? schema.tools.length : 0,
      handoffs: Array.isArray(schema.handoffs) ? schema.handoffs.length : 0,
      interrupts: Array.isArray(schema.interrupt_triggers)
        ? schema.interrupt_triggers.length
        : 0,
    }
  } catch {
    return { conditions: 0, tools: 0, handoffs: 0, interrupts: 0 }
  }
}
