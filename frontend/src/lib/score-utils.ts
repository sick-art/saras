/**
 * Shared score evaluation utilities used across eval components.
 */

export type ScoreStatus = "pass" | "warn" | "fail"

export interface ScoreInfo {
  status: ScoreStatus
  label: string
  color: string
  textClass: string
  bgClass: string
  dotClass: string
}

/** Threshold: >= 0.8 PASS, >= 0.5 WARN, < 0.5 FAIL */
export function getScoreStatus(score: number): ScoreInfo {
  if (score >= 0.8) {
    return {
      status: "pass",
      label: "PASS",
      color: "emerald",
      textClass: "text-emerald-600",
      bgClass: "bg-emerald-500/10 text-emerald-600",
      dotClass: "bg-emerald-500",
    }
  }
  if (score >= 0.5) {
    return {
      status: "warn",
      label: "WARN",
      color: "amber",
      textClass: "text-amber-600",
      bgClass: "bg-amber-500/10 text-amber-600",
      dotClass: "bg-amber-500",
    }
  }
  return {
    status: "fail",
    label: "FAIL",
    color: "red",
    textClass: "text-red-600",
    bgClass: "bg-red-500/10 text-red-600",
    dotClass: "bg-red-500",
  }
}

/** Returns just the text color class for a score */
export function scoreTextClass(score: number): string {
  return getScoreStatus(score).textClass
}

/** Returns bg + text class for a score badge */
export function scoreBadgeClass(score: number): string {
  return getScoreStatus(score).bgClass
}

/** Whether all scores in the array pass (>= 0.8) */
export function allScoresPass(scores: number[]): boolean {
  return scores.length > 0 && scores.every(s => s >= 0.8)
}

/** Average of an array of numbers */
export function avgScore(scores: number[]): number {
  if (scores.length === 0) return 0
  return scores.reduce((a, b) => a + b, 0) / scores.length
}

/** Format metric_id for display: replace underscores with spaces, title-case */
export function formatMetricName(metricId: string): string {
  return metricId
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase())
}
