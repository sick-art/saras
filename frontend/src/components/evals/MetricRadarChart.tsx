/**
 * MetricRadarChart — radar/spider chart showing all metric scores.
 * Uses recharts RadarChart for multi-metric at-a-glance profiles.
 */

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar,
  ResponsiveContainer,
} from "recharts"
import type { MetricSummary } from "@/types/eval"

interface Props {
  metrics: Record<string, MetricSummary>
  className?: string
}

export function MetricRadarChart({ metrics, className }: Props) {
  const entries = Object.entries(metrics)
  if (entries.length < 3) {
    // Radar chart needs at least 3 axes to look meaningful
    return null
  }

  const data = entries.map(([name, m]) => ({
    metric: name.length > 20 ? name.slice(0, 18) + "..." : name,
    score: parseFloat(m.avg_score.toFixed(2)),
  }))

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="hsl(var(--border))" />
          <PolarAngleAxis
            dataKey="metric"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
          />
          <Radar
            dataKey="score"
            stroke="hsl(var(--primary))"
            fill="hsl(var(--primary))"
            fillOpacity={0.2}
            strokeWidth={2}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}
