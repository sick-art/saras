import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import {
  Plus,
  Trash2,
  Loader2,
  FileText,
  ChevronLeft,
} from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
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
import { api } from "@/lib/api"
import type { DatasetDetail as DatasetDetailType, DatasetItem, ScriptedInput, SimulatedInput } from "@/types/eval"
import { DatasetItemDrawer } from "./DatasetItemDrawer"

function itemMode(item: DatasetItem): "scripted" | "simulated" | "golden" {
  const inp = item.input as Record<string, unknown>
  if ("turns" in inp) return (item.source === "auto" && (item.metadata as Record<string, unknown> | null)?.source_type) ? "golden" : "scripted"
  if ("scenario" in inp) return "simulated"
  return "scripted"
}

function itemTurnCount(item: DatasetItem): number {
  const inp = item.input as Record<string, unknown>
  if ("turns" in inp) return ((inp as unknown as ScriptedInput).turns ?? []).length
  return 0
}

const MODE_LABELS: Record<string, { label: string; className: string }> = {
  scripted: { label: "Scripted", className: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  simulated: { label: "Simulated", className: "bg-purple-500/10 text-purple-600 dark:text-purple-400" },
  golden: { label: "Golden", className: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
}

export function DatasetDetail() {
  const { projectId, datasetId } = useParams<{ projectId: string; datasetId: string }>()
  const [dataset, setDataset] = useState<DatasetDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editItem, setEditItem] = useState<DatasetItem | null>(null)

  const loadDataset = () => {
    if (!projectId || !datasetId) return
    setLoading(true)
    api.get<DatasetDetailType>(`/projects/${projectId}/datasets/${datasetId}`)
      .then(setDataset)
      .finally(() => setLoading(false))
  }

  useEffect(loadDataset, [projectId, datasetId])

  const handleSave = async (input: ScriptedInput | SimulatedInput, expectedTurns?: string[]) => {
    if (!projectId || !datasetId) return
    const body = {
      input,
      expected_output: expectedTurns ? { turns: expectedTurns } : null,
    }
    if (editItem) {
      await api.patch<DatasetItem>(`/projects/${projectId}/datasets/${datasetId}/items/${editItem.id}`, body)
    } else {
      await api.post<DatasetItem>(`/projects/${projectId}/datasets/${datasetId}/items`, body)
    }
    setEditItem(null)
    loadDataset()
  }

  const handleDelete = async (itemId: string) => {
    if (!projectId || !datasetId) return
    await api.delete(`/projects/${projectId}/datasets/${datasetId}/items/${itemId}`)
    setDataset(prev => prev ? { ...prev, items: prev.items.filter(i => i.id !== itemId) } : prev)
  }

  if (loading) {
    return (
      <>
        <TopBar title="Dataset" />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </main>
      </>
    )
  }

  if (!dataset) {
    return (
      <>
        <TopBar title="Dataset not found" />
        <main className="flex-1 p-6">
          <p className="text-muted-foreground">Dataset not found.</p>
        </main>
      </>
    )
  }

  return (
    <>
      <TopBar
        title={dataset.name}
        breadcrumb={
          <Link
            to={`/projects/${projectId}/datasets`}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors text-sm shrink-0"
          >
            <ChevronLeft className="size-4" />
            Datasets
          </Link>
        }
      />
      <main className="flex-1 overflow-y-auto p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">{dataset.name}</h2>
            {dataset.description && (
              <p className="text-sm text-muted-foreground mt-0.5">{dataset.description}</p>
            )}
            <p className="text-sm text-muted-foreground mt-1">
              {dataset.item_count} {dataset.item_count === 1 ? "item" : "items"}
            </p>
          </div>
          <Button onClick={() => { setEditItem(null); setDrawerOpen(true) }}>
            <Plus className="size-4 mr-2" />
            Add item
          </Button>
        </div>

        {/* Items table */}
        {dataset.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
            <FileText className="size-10 text-muted-foreground/40 mb-3" />
            <p className="font-medium text-sm">No items yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Add scripted turns or simulated scenarios. You can also generate golden items from the Simulator or Traces views.
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => setDrawerOpen(true)}>
              <Plus className="size-3.5 mr-1.5" />
              Add item
            </Button>
          </div>
        ) : (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-14">#</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Preview</TableHead>
                  <TableHead className="w-24 text-center">Turns</TableHead>
                  <TableHead className="w-28 text-center">Expected</TableHead>
                  <TableHead className="w-28">Added</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {dataset.items.map((item, idx) => {
                  const mode = itemMode(item)
                  const meta = MODE_LABELS[mode]
                  const inp = item.input as Record<string, unknown>
                  const preview =
                    "turns" in inp
                      ? ((inp as unknown as ScriptedInput).turns ?? [])[0] ?? ""
                      : `${(item.input as SimulatedInput).scenario?.persona?.slice(0, 60)}…`

                  return (
                    <TableRow key={item.id} className="cursor-pointer hover:bg-muted/40">
                      <TableCell className="text-muted-foreground font-mono text-xs">{idx + 1}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${meta.className}`}>
                          {meta.label}
                        </span>
                      </TableCell>
                      <TableCell
                        className="max-w-xs truncate text-sm text-muted-foreground cursor-pointer"
                        onClick={() => { setEditItem(item); setDrawerOpen(true) }}
                      >
                        {preview}
                      </TableCell>
                      <TableCell className="text-center text-sm">
                        {"turns" in inp ? itemTurnCount(item) : "—"}
                      </TableCell>
                      <TableCell className="text-center">
                        {item.expected_output ? (
                          <Badge variant="outline" className="text-xs">Yes</Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <AlertDialog>
                          <AlertDialogTrigger
                            render={
                              <Button
                                variant="ghost"
                                size="icon"
                                className="size-8 text-muted-foreground hover:text-destructive"
                                onClick={e => e.stopPropagation()}
                              />
                            }
                          >
                            <Trash2 className="size-3.5" />
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete item?</AlertDialogTitle>
                              <AlertDialogDescription>
                                This dataset item will be permanently removed.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                className="bg-destructive hover:bg-destructive/90"
                                onClick={() => handleDelete(item.id)}
                              >
                                Delete
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </main>

      <DatasetItemDrawer
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setEditItem(null) }}
        onSave={handleSave}
        initial={editItem}
      />
    </>
  )
}
