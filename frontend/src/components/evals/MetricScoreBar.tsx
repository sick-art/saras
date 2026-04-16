/**
 * MetricScoreBar — horizontal bar showing a single metric score.
 * Pure CSS/Tailwind, no chart library needed for inline bars.
 */

import { cn } from "@/lib/utils"

interface Props {
  name: string
  score: number
  className?: string
}

function barColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500"
  if (score >= 0.5) return "bg-amber-500"
  return "bg-red-500"
}

export function MetricScoreBar({ name, score, className }: Props) {
  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium truncate">{name}</span>
        <span className="tabular-nums text-muted-foreground">{score.toFixed(2)}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", barColor(score))}
          style={{ width: `${Math.max(score * 100, 1)}%` }}
        />
      </div>
    </div>
  )
}
