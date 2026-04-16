/**
 * QuickEvalDialog — trigger a quick eval from a dataset of golden items.
 * Picks an agent + metrics, calls POST /quick-eval, navigates to run detail.
 */

import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Loader2, Play } from "lucide-react"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import type { AgentRecord } from "@/types/agent"
import type { PresetMetric, QuickEvalRequest } from "@/types/eval"

interface Props {
  open: boolean
  onClose: () => void
  datasetId: string
}

const DEFAULT_METRICS = ["semantic_similarity", "tool_call_accuracy"]

export function QuickEvalDialog({ open, onClose, datasetId }: Props) {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [presets, setPresets] = useState<PresetMetric[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState("")
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string>>(new Set(DEFAULT_METRICS))
  const [triggering, setTriggering] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!open || !projectId) return
    setLoading(true)
    Promise.all([
      api.get<AgentRecord[]>(`/projects/${projectId}/agents`),
      api.get<PresetMetric[]>(`/projects/${projectId}/evals/presets`),
    ]).then(([a, p]) => {
      setAgents(a)
      setPresets(p)
      if (a.length > 0) setSelectedAgentId(a[0].id)
    }).finally(() => setLoading(false))
  }, [open, projectId])

  const toggleMetric = (key: string) => {
    setSelectedMetrics(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleRun = async () => {
    if (!projectId || !selectedAgentId) return
    setTriggering(true)
    try {
      const body: QuickEvalRequest = {
        dataset_id: datasetId,
        agent_id: selectedAgentId,
        metrics: Array.from(selectedMetrics),
      }
      const run = await api.post<{ id: string }>(
        `/projects/${projectId}/evals/quick-eval`,
        body
      )
      navigate(`/projects/${projectId}/evals/runs/${run.id}`)
    } finally {
      setTriggering(false)
    }
  }

  const canRun = !triggering && selectedAgentId && selectedMetrics.size > 0

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Quick eval from goldens</DialogTitle>
          <DialogDescription>
            Run an evaluation against this dataset using preset metrics.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading...
            </div>
          ) : (
            <>
              {/* Agent picker */}
              <div className="space-y-1.5">
                <Label className="text-xs">Agent</Label>
                <Select value={selectedAgentId} onValueChange={v => setSelectedAgentId(v ?? "")}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder="Select agent..." />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map(a => (
                      <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Metric toggles */}
              <div className="space-y-1.5">
                <Label className="text-xs">Metrics ({selectedMetrics.size} selected)</Label>
                <div className="space-y-1">
                  {presets.map(p => (
                    <label
                      key={p.key}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/40 cursor-pointer text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={selectedMetrics.has(p.key)}
                        onChange={() => toggleMetric(p.key)}
                        className="rounded border-border"
                      />
                      <span className="flex-1 truncate">{p.name}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {p.type === "llm_judge" ? "LLM judge" : "Deterministic"}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={triggering}>
            Cancel
          </Button>
          <Button onClick={handleRun} disabled={!canRun}>
            {triggering ? (
              <Loader2 className="size-4 mr-2 animate-spin" />
            ) : (
              <Play className="size-4 mr-2" />
            )}
            Run eval
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
