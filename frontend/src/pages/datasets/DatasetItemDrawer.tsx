/**
 * DatasetItemDrawer — slide-in sheet for creating or editing a dataset item.
 *
 * Supports two modes:
 *   Scripted   — user provides a list of turn messages (fixed conversation)
 *   Simulated  — user provides a persona + goal for LLM-driven simulation
 *
 * Optionally accepts expected_output.turns for golden reference comparison.
 */

import { useState } from "react"
import { Plus, Trash2, Loader2 } from "lucide-react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import type { DatasetItem, ScriptedInput, SimulatedInput } from "@/types/eval"

interface Props {
  open: boolean
  onClose: () => void
  onSave: (input: ScriptedInput | SimulatedInput, expectedTurns?: string[]) => Promise<void>
  initial?: DatasetItem | null
}

export function DatasetItemDrawer({ open, onClose, onSave, initial }: Props) {
  const isScripted = !initial || "turns" in (initial?.input ?? {})
  const [mode, setMode] = useState<"scripted" | "simulated">(isScripted ? "scripted" : "simulated")
  const [saving, setSaving] = useState(false)

  // Scripted state
  const initTurns = (initial?.input as ScriptedInput | undefined)?.turns ?? [""]
  const [turns, setTurns] = useState<string[]>(initTurns)

  // Simulated state
  const initScenario = (initial?.input as SimulatedInput | undefined)?.scenario
  const [persona, setPersona] = useState(initScenario?.persona ?? "")
  const [goal, setGoal] = useState(initScenario?.goal ?? "")
  const [maxTurns, setMaxTurns] = useState(initScenario?.max_turns ?? 8)
  const [stopSignal, setStopSignal] = useState(initScenario?.stop_signal ?? "")

  // Expected output (optional golden)
  const initExpected = (initial?.expected_output as { turns?: string[] } | null | undefined)?.turns ?? []
  const [showExpected, setShowExpected] = useState(initExpected.length > 0)
  const [expectedTurns, setExpectedTurns] = useState<string[]>(initExpected)

  const updateTurn = (idx: number, val: string) => {
    setTurns(prev => prev.map((t, i) => i === idx ? val : t))
  }

  const addTurn = () => setTurns(prev => [...prev, ""])
  const removeTurn = (idx: number) => setTurns(prev => prev.filter((_, i) => i !== idx))

  const updateExpected = (idx: number, val: string) => {
    setExpectedTurns(prev => prev.map((t, i) => i === idx ? val : t))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      let input: ScriptedInput | SimulatedInput
      if (mode === "scripted") {
        input = { turns: turns.filter(t => t.trim()) }
      } else {
        input = {
          scenario: {
            persona: persona.trim(),
            goal: goal.trim(),
            max_turns: maxTurns,
            stop_signal: stopSignal.trim() || null,
          },
        }
      }
      const expected = showExpected ? expectedTurns.filter(t => t.trim()) : undefined
      await onSave(input, expected?.length ? expected : undefined)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  const canSave =
    mode === "scripted"
      ? turns.some(t => t.trim())
      : persona.trim() && goal.trim()

  return (
    <Sheet open={open} onOpenChange={v => !v && onClose()}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto flex flex-col">
        <SheetHeader>
          <SheetTitle>{initial ? "Edit item" : "Add dataset item"}</SheetTitle>
        </SheetHeader>

        <div className="flex-1 space-y-5 py-4">
          <Tabs value={mode} onValueChange={v => setMode(v as "scripted" | "simulated")}>
            <TabsList className="w-full">
              <TabsTrigger value="scripted" className="flex-1">Scripted turns</TabsTrigger>
              <TabsTrigger value="simulated" className="flex-1">Simulated scenario</TabsTrigger>
            </TabsList>

            {/* ── Scripted ─────────────────────────────────────────────────── */}
            <TabsContent value="scripted" className="mt-4 space-y-3">
              <p className="text-xs text-muted-foreground">
                Define the exact user messages for each turn. The agent is replayed against these fixed inputs.
              </p>
              {turns.map((turn, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="mt-2.5 text-xs font-mono text-muted-foreground w-5 shrink-0 text-right">
                    {idx + 1}
                  </span>
                  <Textarea
                    className="flex-1 resize-none text-sm"
                    rows={2}
                    placeholder={`User message ${idx + 1}…`}
                    value={turn}
                    onChange={e => updateTurn(idx, e.target.value)}
                  />
                  {turns.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="mt-1 size-8 text-muted-foreground hover:text-destructive"
                      onClick={() => removeTurn(idx)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  )}
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={addTurn} className="w-full">
                <Plus className="size-3.5 mr-1.5" />
                Add turn
              </Button>
            </TabsContent>

            {/* ── Simulated ─────────────────────────────────────────────────── */}
            <TabsContent value="simulated" className="mt-4 space-y-4">
              <p className="text-xs text-muted-foreground">
                An LLM will roleplay as this user persona and generate messages dynamically to achieve the goal.
              </p>
              <div className="space-y-1.5">
                <Label>Persona</Label>
                <Textarea
                  rows={3}
                  placeholder="e.g. Frustrated customer who bought a defective product and wants a refund, but doesn't know their order number"
                  value={persona}
                  onChange={e => setPersona(e.target.value)}
                  className="text-sm resize-none"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Goal</Label>
                <Textarea
                  rows={2}
                  placeholder="e.g. Get a full refund for order #12345"
                  value={goal}
                  onChange={e => setGoal(e.target.value)}
                  className="text-sm resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Max turns</Label>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={maxTurns}
                    onChange={e => setMaxTurns(parseInt(e.target.value) || 8)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>
                    Stop signal <span className="text-muted-foreground">(optional)</span>
                  </Label>
                  <Input
                    placeholder="e.g. User says thank you"
                    value={stopSignal}
                    onChange={e => setStopSignal(e.target.value)}
                  />
                </div>
              </div>
            </TabsContent>
          </Tabs>

          {/* ── Golden expected output (optional) ──────────────────────────── */}
          {mode === "scripted" && (
            <div className="border-t pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Golden expected output</p>
                  <p className="text-xs text-muted-foreground">
                    Reference agent responses for ROUGE / semantic similarity scoring.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setShowExpected(v => !v)
                    if (!showExpected) setExpectedTurns(turns.map(() => ""))
                  }}
                >
                  {showExpected ? "Remove" : "Add"}
                </Button>
              </div>
              {showExpected && (
                <div className="space-y-2">
                  {turns.map((_, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      <span className="mt-2.5 text-xs font-mono text-muted-foreground w-5 shrink-0 text-right">
                        {idx + 1}
                      </span>
                      <Textarea
                        className="flex-1 resize-none text-sm"
                        rows={2}
                        placeholder={`Expected agent response for turn ${idx + 1}…`}
                        value={expectedTurns[idx] ?? ""}
                        onChange={e => updateExpected(idx, e.target.value)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <SheetFooter className="border-t pt-4">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={!canSave || saving}>
            {saving && <Loader2 className="size-4 mr-2 animate-spin" />}
            {initial ? "Save changes" : "Add item"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
