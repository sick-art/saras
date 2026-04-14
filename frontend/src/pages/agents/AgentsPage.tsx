import { useEffect, useState, useCallback } from "react"
import { Link, useParams, useNavigate } from "react-router-dom"
import {
  Bot,
  Plus,
  ExternalLink,
  Clock,
  AlertCircle,
  Loader2,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Trash2,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button, buttonVariants } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardAction,
} from "@/components/ui/card"
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { AgentRecord } from "@/types/agent"

// ── API types ──────────────────────────────────────────────────────────────────

interface SampleMeta {
  slug: string
  name: string
  description: string
  tags: string[]
  complexity: "starter" | "intermediate" | "full"
}

// ── Agent list card ────────────────────────────────────────────────────────────

function AgentCard({
  agent,
  projectId,
  onDelete,
}: {
  agent: AgentRecord
  projectId: string
  onDelete: (id: string) => Promise<void>
}) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const updatedAt = new Date(agent.updated_at)
  const timeAgo = formatRelative(updatedAt)

  async function handleDelete() {
    setDeleting(true)
    try {
      await onDelete(agent.id)
    } catch {
      setDeleting(false)
      setConfirmOpen(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="size-4 text-muted-foreground shrink-0" />
          <span className="truncate">{agent.name}</span>
          {agent.is_published && (
            <Badge variant="secondary" className="ml-auto shrink-0">
              Published
            </Badge>
          )}
        </CardTitle>
        {agent.description && (
          <CardDescription className="line-clamp-2">{agent.description}</CardDescription>
        )}
        <CardAction>
          <span className="text-xs text-muted-foreground">v{agent.current_version}</span>
        </CardAction>
      </CardHeader>

      <CardContent>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="size-3" />
          {timeAgo}
        </div>
      </CardContent>

      <CardFooter className="flex gap-2">
        <Link
          to={`/projects/${projectId}/agents/${agent.id}`}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}
        >
          View
          <ChevronRight data-icon="inline-end" />
        </Link>
        <Link
          to={`/projects/${projectId}/agents/${agent.id}/builder`}
          className={cn(buttonVariants({ size: "sm" }), "flex-1")}
        >
          Open Builder
          <ExternalLink data-icon="inline-end" />
        </Link>

        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogTrigger
            render={
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
              />
            }
          >
            <Trash2 />
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete "{agent.name}"?</AlertDialogTitle>
              <AlertDialogDescription>
                This agent and all its version history will be permanently deleted. This cannot be
                undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
              <AlertDialogAction variant="destructive" disabled={deleting} onClick={handleDelete}>
                {deleting && <Loader2 className="animate-spin" data-icon="inline-start" />}
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardFooter>
    </Card>
  )
}

// ── Skeleton loader ────────────────────────────────────────────────────────────

function AgentCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-full mt-2" />
        <Skeleton className="h-3 w-4/5 mt-1" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-3 w-24" />
      </CardContent>
      <CardFooter className="flex gap-2">
        <Skeleton className="h-8 flex-1" />
        <Skeleton className="h-8 flex-1" />
        <Skeleton className="size-8 shrink-0" />
      </CardFooter>
    </Card>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export function AgentsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [samples, setSamples] = useState<SampleMeta[]>([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [loadingSamples, setLoadingSamples] = useState(true)
  const [cloningSlug, setCloningSlug] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Fetch agents
  useEffect(() => {
    if (!projectId) return
    setLoadingAgents(true)
    api
      .get<AgentRecord[]>(`/projects/${projectId}/agents`)
      .then(setAgents)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingAgents(false))
  }, [projectId])

  // Fetch sample templates (used in dropdown only)
  useEffect(() => {
    api
      .get<SampleMeta[]>("/samples")
      .then(setSamples)
      .catch(() => setSamples([]))
      .finally(() => setLoadingSamples(false))
  }, [])

  const handleClone = useCallback(
    async (slug: string) => {
      if (!projectId || cloningSlug) return
      setCloningSlug(slug)
      try {
        const created = await api.post<AgentRecord>(
          `/projects/${projectId}/agents/clone-sample`,
          { slug },
        )
        setAgents((prev) => [created, ...prev])
        navigate(`/projects/${projectId}/agents/${created.id}/builder`)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Clone failed")
      } finally {
        setCloningSlug(null)
      }
    },
    [cloningSlug, navigate, projectId],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      await api.delete(`/projects/${projectId}/agents/${id}`)
      setAgents((prev) => prev.filter((a) => a.id !== id))
    },
    [projectId],
  )

  const hasAgents = agents.length > 0
  const samplesReady = !loadingSamples && samples.length > 0

  return (
    <>
      <TopBar title="Agents" />
      <main className="flex-1 overflow-y-auto p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">Agents</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Build and manage conversational agents for your project.
            </p>
          </div>

          {/* Split: New Agent + sample dropdown */}
          <div className="flex items-center">
            <Link
              to={`/projects/${projectId}/agents/new`}
              className={cn(
                buttonVariants({ size: "sm" }),
                samplesReady && "rounded-r-none",
              )}
            >
              <Plus data-icon="inline-start" />
              New Agent
            </Link>
            {samplesReady && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      size="sm"
                      className="rounded-l-none border-l border-l-primary-foreground/20 px-1.5"
                    />
                  }
                  disabled={!!cloningSlug}
                >
                  {cloningSlug ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <ChevronDown className="size-3" />
                  )}
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-44">
                  <DropdownMenuLabel>From sample</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {samples.map((sample) => (
                    <DropdownMenuItem
                      key={sample.slug}
                      disabled={!!cloningSlug}
                      onClick={() => handleClone(sample.slug)}
                    >
                      <Sparkles />
                      {sample.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertCircle className="size-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Agent list */}
        {loadingAgents ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => <AgentCardSkeleton key={i} />)}
          </div>
        ) : hasAgents ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                projectId={projectId!}
                onDelete={handleDelete}
              />
            ))}
          </div>
        ) : null}

        {/* Empty state */}
        {!loadingAgents && !hasAgents && (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
            <Bot className="size-10 text-muted-foreground/40 mb-3" />
            <p className="font-medium text-sm">No agents yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Create your first agent from scratch or start from a sample using the button above.
            </p>
            <Link
              to={`/projects/${projectId}/agents/new`}
              className={cn(buttonVariants(), "mt-4")}
            >
              <Plus data-icon="inline-start" />
              Create agent
            </Link>
          </div>
        )}
      </main>
    </>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatRelative(date: Date): string {
  const diff = Date.now() - date.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return date.toLocaleDateString()
}
