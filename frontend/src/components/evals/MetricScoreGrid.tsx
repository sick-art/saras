/**
 * MetricScoreGrid — grid of MetricScoreBar + optional radar chart
 * for visualizing all metric summaries from an EvalRunSummary.
 */

import { MetricScoreBar } from "./MetricScoreBar"
import { MetricRadarChart } from "./MetricRadarChart"
import type { MetricSummary } from "@/types/eval"

interface Props {
  metrics: Record<string, MetricSummary>
  showRadar?: boolean
}

export function MetricScoreGrid({ metrics, showRadar = true }: Props) {
  const entries = Object.entries(metrics)
  if (entries.length === 0) return null

  return (
    <div className="space-y-4">
      {showRadar && <MetricRadarChart metrics={metrics} />}

      <div className="space-y-2">
        {entries.map(([name, m]) => (
          <MetricScoreBar key={name} name={name} score={m.avg_score} />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Pass Rate</p>
          <p className="text-sm font-semibold tabular-nums">
            {Math.round(
              (entries.reduce((s, [, m]) => s + m.pass_rate, 0) / entries.length) * 100
            )}%
          </p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Lowest</p>
          <p className="text-sm font-semibold tabular-nums">
            {Math.round(Math.min(...entries.map(([, m]) => m.min_score)) * 100)}%
          </p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Highest</p>
          <p className="text-sm font-semibold tabular-nums">
            {Math.round(Math.max(...entries.map(([, m]) => m.max_score)) * 100)}%
          </p>
        </div>
      </div>
    </div>
  )
}
