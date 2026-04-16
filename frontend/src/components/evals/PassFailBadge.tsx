/**
 * PassFailBadge — renders a colored PASS / WARN / FAIL pill.
 */

import { getScoreStatus } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  score: number
  className?: string
  /** Show the numeric score next to the label */
  showScore?: boolean
}

export function PassFailBadge({ score, className, showScore = false }: Props) {
  const { label, bgClass } = getScoreStatus(score)

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold",
        bgClass,
        className,
      )}
    >
      {showScore && <span className="tabular-nums">{score.toFixed(2)}</span>}
      {label}
    </span>
  )
}
