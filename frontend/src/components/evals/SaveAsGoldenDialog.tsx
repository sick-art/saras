/**
 * SaveAsGoldenDialog — saves a conversation as a golden dataset item.
 *
 * Can be called from two sources:
 *   - SimulatorLayout: passes `history` (OpenAI messages) + `agentId`
 *   - SessionDetail: passes `sessionId`
 *
 * The user picks an existing dataset or creates a new one inline.
 */

import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { Plus, Loader2, BookOpen, Check } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import type { Dataset, DatasetItem } from "@/types/eval"

interface HistorySource {
  kind: "simulation"
  history: Array<{ role: string; content: string }>
  agentId?: string
}

interface SessionSource {
  kind: "session"
  sessionId: string
}

export type GoldenSource = HistorySource | SessionSource

interface Props {
  open: boolean
  onClose: () => void
  source: GoldenSource
}

export function SaveAsGoldenDialog({ open, onClose, source }: Props) {
  const { projectId } = useParams<{ projectId: string }>()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loadingDatasets, setLoadingDatasets] = useState(true)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("")
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState("")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!open || !projectId) return
    setLoadingDatasets(true)
    setSaved(false)
    api.get<Dataset[]>(`/projects/${projectId}/datasets`)
      .then(ds => {
        setDatasets(ds)
        if (ds.length > 0) setSelectedDatasetId(ds[0].id)
      })
      .finally(() => setLoadingDatasets(false))
  }, [open, projectId])

  // Preview: count user messages
  const userTurnCount =
    source.kind === "simulation"
      ? source.history.filter(m => m.role === "user").length
      : null

  const handleSave = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      let datasetId = selectedDatasetId

      // Create new dataset if requested
      if (showNew && newName.trim()) {
        const created = await api.post<Dataset>(`/projects/${projectId}/datasets`, {
          name: newName.trim(),
        })
        datasetId = created.id
        setDatasets(prev => [created, ...prev])
      }

      if (!datasetId) return

      if (source.kind === "simulation") {
        await api.post<DatasetItem>(
          `/projects/${projectId}/datasets/${datasetId}/items/from-simulation`,
          {
            history: source.history,
            agent_id: source.agentId ?? null,
            metadata: { source_type: "simulation" },
          }
        )
      } else {
        await api.post<DatasetItem>(
          `/projects/${projectId}/datasets/${datasetId}/items/from-session`,
          { session_id: source.sessionId }
        )
      }
      setSaved(true)
      setTimeout(onClose, 1200)
    } finally {
      setSaving(false)
    }
  }

  const canSave =
    !saving &&
    (showNew ? newName.trim().length > 0 : selectedDatasetId.length > 0)

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Save as golden</DialogTitle>
          <DialogDescription>
            {source.kind === "simulation"
              ? `Save this ${userTurnCount ? `${userTurnCount}-turn ` : ""}conversation as a golden dataset item for regression testing.`
              : "Save this session as a golden dataset item."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {loadingDatasets ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading datasets…
            </div>
          ) : (
            <>
              {!showNew && (
                <div className="space-y-1.5">
                  <Label>Dataset</Label>
                  {datasets.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No datasets yet — create one below.</p>
                  ) : (
                    <Select value={selectedDatasetId} onValueChange={v => setSelectedDatasetId(v ?? "")}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select dataset…" />
                      </SelectTrigger>
                      <SelectContent>
                        {datasets.map(d => (
                          <SelectItem key={d.id} value={d.id}>
                            {d.name}
                            <span className="ml-2 text-xs text-muted-foreground">
                              ({d.item_count} items)
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto p-0 text-xs"
                    onClick={() => setShowNew(true)}
                  >
                    <Plus className="size-3 mr-1" />
                    Create new dataset
                  </Button>
                </div>
              )}

              {showNew && (
                <div className="space-y-1.5">
                  <Label>New dataset name</Label>
                  <Input
                    placeholder="e.g. Customer support goldens"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    autoFocus
                  />
                  {datasets.length > 0 && (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-xs"
                      onClick={() => setShowNew(false)}
                    >
                      Use existing dataset instead
                    </Button>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            {saved ? (
              <>
                <Check className="size-4 mr-2 text-green-500" />
                Saved!
              </>
            ) : saving ? (
              <>
                <Loader2 className="size-4 mr-2 animate-spin" />
                Saving…
              </>
            ) : (
              <>
                <BookOpen className="size-4 mr-2" />
                Save golden
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
