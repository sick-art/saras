import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Database, Plus, Loader2, FileText } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import type { Dataset } from "@/types/eval"

export function DatasetsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  useEffect(() => {
    if (!projectId) return
    api.get<Dataset[]>(`/projects/${projectId}/datasets`)
      .then(setDatasets)
      .finally(() => setLoading(false))
  }, [projectId])

  const handleCreate = async () => {
    if (!projectId || !name.trim()) return
    setCreating(true)
    try {
      const created = await api.post<Dataset>(`/projects/${projectId}/datasets`, {
        name: name.trim(),
        description: description.trim() || null,
      })
      setDatasets(prev => [created, ...prev])
      setShowCreate(false)
      setName("")
      setDescription("")
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <TopBar title="Datasets" />
      <main className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">Datasets</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage golden examples and test cases for evaluation.
            </p>
          </div>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="size-4 mr-2" />
            New dataset
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : datasets.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
            <Database className="size-10 text-muted-foreground/40 mb-3" />
            <p className="font-medium text-sm">No datasets yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Datasets are built from simulations, observability logs, or manually curated examples.
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => setShowCreate(true)}>
              <Plus className="size-3.5 mr-1.5" />
              Create dataset
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {datasets.map(d => (
              <Link key={d.id} to={`/projects/${projectId}/datasets/${d.id}`}>
                <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-base font-medium line-clamp-1">{d.name}</CardTitle>
                      <Badge variant="secondary" className="shrink-0 text-xs">
                        <FileText className="size-3 mr-1" />
                        {d.item_count} {d.item_count === 1 ? "item" : "items"}
                      </Badge>
                    </div>
                    {d.description && (
                      <CardDescription className="line-clamp-2">{d.description}</CardDescription>
                    )}
                  </CardHeader>
                  <CardContent className="pt-0">
                    <p className="text-xs text-muted-foreground">
                      Created {new Date(d.created_at).toLocaleDateString()}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New dataset</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="ds-name">Name</Label>
              <Input
                id="ds-name"
                placeholder="e.g. Customer support golden set"
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ds-desc">Description <span className="text-muted-foreground">(optional)</span></Label>
              <Textarea
                id="ds-desc"
                placeholder="What this dataset is used for…"
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
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
