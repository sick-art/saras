import { useEffect, useState, useCallback } from "react"
import { Link, useParams } from "react-router-dom"
import {
  FlaskConical,
  Plus,
  Loader2,
  Trash2,
  LayoutGrid,
  List,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { EvalSuite } from "@/types/eval"

const DEFAULT_YAML = `metrics:
  - preset: goal_completion
  - preset: hallucination_detection
  - preset: tool_call_accuracy
`

const LAYOUT_KEY = "saras:evals:layout"

type LayoutMode = "grid" | "list"

function getStoredLayout(): LayoutMode {
  try {
    const v = localStorage.getItem(LAYOUT_KEY)
    if (v === "list") return "list"
  } catch {
    /* ignore */
  }
  return "grid"
}

// ── Suite card (grid view) ──────────────────────────────────────────────────

function SuiteCard({
  suite,
  projectId,
  onDelete,
}: {
  suite: EvalSuite
  projectId: string
  onDelete: (id: string) => Promise<void>
}) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    setDeleting(true)
    try {
      await onDelete(suite.id)
    } catch {
      setDeleting(false)
      setConfirmOpen(false)
    }
  }

  return (
    <Card className="hover:border-primary/50 transition-colors h-full flex flex-col">
      <Link to={`/projects/${projectId}/evals/suites/${suite.id}`} className="flex-1">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium line-clamp-1">{suite.name}</CardTitle>
          {suite.description && (
            <CardDescription className="line-clamp-2">{suite.description}</CardDescription>
          )}
        </CardHeader>
        <CardContent className="pt-0 flex items-center justify-between">
          <Badge variant="secondary" className="text-xs">
            <FlaskConical className="size-3 mr-1" />
            {suite.run_count} {suite.run_count === 1 ? "run" : "runs"}
          </Badge>
          <p className="text-xs text-muted-foreground">
            {new Date(suite.created_at).toLocaleDateString()}
          </p>
        </CardContent>
      </Link>

      <div className="px-6 pb-4 pt-0 flex justify-end">
        <DeleteSuiteButton
          suite={suite}
          confirmOpen={confirmOpen}
          setConfirmOpen={setConfirmOpen}
          deleting={deleting}
          onDelete={handleDelete}
        />
      </div>
    </Card>
  )
}

// ── Suite row (list view) ───────────────────────────────────────────────────

function SuiteRow({
  suite,
  projectId,
  onDelete,
}: {
  suite: EvalSuite
  projectId: string
  onDelete: (id: string) => Promise<void>
}) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    setDeleting(true)
    try {
      await onDelete(suite.id)
    } catch {
      setDeleting(false)
      setConfirmOpen(false)
    }
  }

  return (
    <div className="flex items-center gap-4 rounded-lg border px-4 py-3 hover:border-primary/50 hover:bg-muted/30 transition-colors">
      <Link
        to={`/projects/${projectId}/evals/suites/${suite.id}`}
        className="flex-1 flex items-center gap-4 min-w-0"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{suite.name}</p>
          {suite.description && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{suite.description}</p>
          )}
        </div>
        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
          {suite.run_count} {suite.run_count === 1 ? "run" : "runs"}
        </span>
        <span className="text-xs text-muted-foreground shrink-0">
          {new Date(suite.created_at).toLocaleDateString()}
        </span>
      </Link>
      <DeleteSuiteButton
        suite={suite}
        confirmOpen={confirmOpen}
        setConfirmOpen={setConfirmOpen}
        deleting={deleting}
        onDelete={handleDelete}
      />
    </div>
  )
}

// ── Shared delete button ────────────────────────────────────────────────────

function DeleteSuiteButton({
  suite,
  confirmOpen,
  setConfirmOpen,
  deleting,
  onDelete,
}: {
  suite: EvalSuite
  confirmOpen: boolean
  setConfirmOpen: (v: boolean) => void
  deleting: boolean
  onDelete: () => Promise<void>
}) {
  return (
    <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
      <AlertDialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          />
        }
      >
        <Trash2 className="size-4" />
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete "{suite.name}"?</AlertDialogTitle>
          <AlertDialogDescription>
            This eval suite and all its runs and results will be permanently deleted. This cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={deleting} onClick={onDelete}>
            {deleting && <Loader2 className="animate-spin" data-icon="inline-start" />}
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────

export function EvalsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [suites, setSuites] = useState<EvalSuite[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [layout, setLayout] = useState<LayoutMode>(getStoredLayout)

  useEffect(() => {
    if (!projectId) return
    api
      .get<EvalSuite[]>(`/projects/${projectId}/evals/suites`)
      .then(setSuites)
      .finally(() => setLoading(false))
  }, [projectId])

  const handleCreate = async () => {
    if (!projectId || !name.trim()) return
    setCreating(true)
    try {
      const created = await api.post<EvalSuite>(`/projects/${projectId}/evals/suites`, {
        name: name.trim(),
        description: description.trim() || null,
        metric_set_yaml: DEFAULT_YAML,
      })
      setSuites(prev => [created, ...prev])
      setShowCreate(false)
      setName("")
      setDescription("")
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = useCallback(
    async (id: string) => {
      await api.delete(`/projects/${projectId}/evals/suites/${id}`)
      setSuites(prev => prev.filter(s => s.id !== id))
    },
    [projectId],
  )

  const toggleLayout = (mode: LayoutMode) => {
    setLayout(mode)
    try {
      localStorage.setItem(LAYOUT_KEY, mode)
    } catch {
      /* ignore */
    }
  }

  return (
    <>
      <TopBar title="Evaluations" />
      <main className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">Evaluations</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Define metric sets and run LLM-as-judge evaluations against datasets.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Layout toggle */}
            {suites.length > 0 && (
              <div className="flex items-center rounded-md border p-0.5">
                <button
                  className={cn(
                    "p-1 rounded-sm transition-colors",
                    layout === "grid"
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  onClick={() => toggleLayout("grid")}
                  title="Grid view"
                >
                  <LayoutGrid className="size-4" />
                </button>
                <button
                  className={cn(
                    "p-1 rounded-sm transition-colors",
                    layout === "list"
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  onClick={() => toggleLayout("list")}
                  title="List view"
                >
                  <List className="size-4" />
                </button>
              </div>
            )}
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="size-4 mr-2" />
              New eval suite
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : suites.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
            <FlaskConical className="size-10 text-muted-foreground/40 mb-3" />
            <p className="font-medium text-sm">No eval suites yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Create an eval suite to measure agent quality using preset and custom metrics.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => setShowCreate(true)}
            >
              <Plus className="size-3.5 mr-1.5" />
              Create eval suite
            </Button>
          </div>
        ) : layout === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {suites.map(s => (
              <SuiteCard
                key={s.id}
                suite={s}
                projectId={projectId!}
                onDelete={handleDelete}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {suites.map(s => (
              <SuiteRow
                key={s.id}
                suite={s}
                projectId={projectId!}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New eval suite</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input
                placeholder="e.g. Customer support quality"
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div className="space-y-1.5">
              <Label>
                Description <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                placeholder="What this suite measures…"
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!name.trim() || creating}>
              {creating && <Loader2 className="size-4 mr-2 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
