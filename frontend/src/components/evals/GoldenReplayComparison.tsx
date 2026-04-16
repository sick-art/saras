/**
 * GoldenReplayComparison — side-by-side view comparing golden expected
 * output with actual replay responses, with per-turn metric scores.
 */

import { User, Bot } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ItemResults, EvalResult } from "@/types/eval"

function scoreBg(score: number): string {
  if (score >= 0.8) return "bg-emerald-500/10 text-emerald-600"
  if (score >= 0.5) return "bg-amber-500/10 text-amber-600"
  return "bg-red-500/10 text-red-600"
}

interface Props {
  item: ItemResults
}

export function GoldenReplayComparison({ item }: Props) {
  const turns = item.conversation?.turns ?? []
  const expectedTurns = item.expected_output?.turns ?? []
  const perTurnScores = item.scores.filter(
    s => s.scope === "per_turn" || s.scope === "tool_call"
  )

  if (turns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Bot className="size-8 text-muted-foreground/30 mb-2" />
        <p className="text-sm text-muted-foreground">No conversation data</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 py-4 px-1">
      {/* Header */}
      <div className="grid grid-cols-2 gap-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <span>Expected (Golden)</span>
        <span>Actual (Replay)</span>
      </div>

      {turns.map(turn => {
        const expected = expectedTurns[turn.turn_index] ?? null
        const turnScores = perTurnScores.filter(s => s.turn_index === turn.turn_index)
        const hasDiff = expected !== null && expected !== turn.agent_content

        return (
          <div key={turn.turn_index} className="space-y-2">
            {/* User message */}
            <div className="flex items-start gap-2">
              <div className="size-6 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                <User className="size-3.5 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-muted-foreground font-medium mb-0.5">User</p>
                <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                  {turn.user_message}
                </div>
              </div>
            </div>

            {/* Agent comparison */}
            <div className="grid grid-cols-2 gap-3">
              {/* Golden */}
              <div className="flex items-start gap-2">
                <div className="size-6 rounded-full border bg-card flex items-center justify-center shrink-0 mt-0.5">
                  <Bot className="size-3.5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-muted-foreground font-medium mb-0.5">
                    Turn {turn.turn_index + 1}
                  </p>
                  <div
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm",
                      hasDiff ? "border-border" : "border-emerald-500/30 bg-emerald-500/5"
                    )}
                  >
                    {expected ?? <span className="text-muted-foreground italic">No golden</span>}
                  </div>
                </div>
              </div>

              {/* Actual */}
              <div className="flex items-start gap-2">
                <div className="size-6 rounded-full border bg-card flex items-center justify-center shrink-0 mt-0.5">
                  <Bot className="size-3.5 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-muted-foreground font-medium mb-0.5">Replay</p>
                  <div
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm",
                      hasDiff ? "border-amber-500/30 bg-amber-500/5" : "border-emerald-500/30 bg-emerald-500/5"
                    )}
                  >
                    {turn.agent_content}
                  </div>
                </div>
              </div>
            </div>

            {/* Per-turn scores */}
            {turnScores.length > 0 && (
              <div className="flex flex-wrap gap-1 ml-8">
                {turnScores.map(s => (
                  <span
                    key={s.id}
                    className={cn(
                      "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium",
                      scoreBg(s.score ?? 0)
                    )}
                    title={s.reasoning ?? ""}
                  >
                    {s.metric_id}: {s.score !== null ? s.score.toFixed(2) : "—"}
                  </span>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
