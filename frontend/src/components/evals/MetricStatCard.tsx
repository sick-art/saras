/**
 * MetricStatCard — compact card showing metric name, score, and PASS/FAIL badge.
 * Used in the EvalRunDetail summary banner.
 */

import { getScoreStatus, formatMetricName } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  metricId: string
  avgScore: number
  className?: string
}

export function MetricStatCard({ metricId, avgScore, className }: Props) {
  const { label, textClass, dotClass } = getScoreStatus(avgScore)

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 min-w-[140px] flex flex-col gap-1",
        className,
      )}
    >
      <p className="text-xs font-medium text-muted-foreground truncate" title={formatMetricName(metricId)}>
        {formatMetricName(metricId)}
      </p>
      <p className={cn("text-xl font-bold tabular-nums", textClass)}>
        {avgScore.toFixed(2)}
      </p>
      <div className="flex items-center gap-1.5">
        <span className={cn("size-2 rounded-full", dotClass)} />
        <span className={cn("text-xs font-semibold", textClass)}>{label}</span>
      </div>
    </div>
  )
}
