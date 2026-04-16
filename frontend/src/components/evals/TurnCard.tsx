/**
 * TurnCard — displays a single conversation turn with inline scores.
 *
 * Progressive disclosure:
 *   - All-pass turns (all scores >= 0.8): scores collapsed, "All N metrics passed"
 *   - Turns with issues: scores auto-expanded, reasoning shown for scores < 0.8
 */

import { useState } from "react"
import {
  AlertTriangle,
  ArrowRightLeft,
  Bot,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  Info,
  User,
  Wrench,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  allScoresPass,
  avgScore as calcAvg,
  formatMetricName,
  getScoreStatus,
  scoreBadgeClass,
  scoreTextClass,
} from "@/lib/score-utils"
import { PassFailBadge } from "./PassFailBadge"
import type { EvalResult, TurnRecord } from "@/types/eval"

// ── Turn type config ──────────────────────────────────────────────────────────

const TURN_LABEL: Record<string, string> = {
  slot_fill: "slot fill",
  interrupt: "interrupt",
  handoff: "handoff",
}

const TURN_ACCENT: Record<string, string> = {
  response: "",
  slot_fill: "border-l-amber-400",
  interrupt: "border-l-red-400",
  handoff: "border-l-purple-400",
}

const TURN_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  response: Bot,
  slot_fill: Info,
  interrupt: AlertTriangle,
  handoff: ArrowRightLeft,
}

// ── Score row (expandable reasoning) ──────────────────────────────────────────

function ScoreRow({ result }: { result: EvalResult }) {
  const hasIssue = (result.score ?? 0) < 0.8
  const [showReasoning, setShowReasoning] = useState(hasIssue)
  const info = getScoreStatus(result.score ?? 0)

  return (
    <div className="group">
      <button
        className="w-full flex items-center justify-between py-1.5 text-left hover:bg-muted/40 rounded px-2 -mx-2 transition-colors"
        onClick={() => setShowReasoning(v => !v)}
        disabled={!result.reasoning}
      >
        <span className="text-xs text-foreground">{formatMetricName(result.metric_id)}</span>
        <div className="flex items-center gap-2">
          <span className={cn("text-xs font-semibold tabular-nums", info.textClass)}>
            {result.score !== null ? result.score.toFixed(2) : "—"}
          </span>
          <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded", info.bgClass)}>
            {info.label}
          </span>
          {result.reasoning && (
            showReasoning
              ? <ChevronDown className="size-3 text-muted-foreground" />
              : <ChevronRight className="size-3 text-muted-foreground" />
          )}
        </div>
      </button>
      {showReasoning && result.reasoning && (
        <div className="pl-2 pr-2 pb-1.5">
          <p className="text-[11px] text-muted-foreground leading-relaxed">{result.reasoning}</p>
          {result.model_used && (
            <p className="text-[10px] text-muted-foreground/60 mt-1">Model: {result.model_used}</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── TurnCard ──────────────────────────────────────────────────────────────────

interface Props {
  turn: TurnRecord
  scores: EvalResult[]
}

export function TurnCard({ turn, scores }: Props) {
  const scoreValues = scores.map(s => s.score ?? 0)
  const avg = calcAvg(scoreValues)
  const isAllPass = allScoresPass(scoreValues)
  const [scoresOpen, setScoresOpen] = useState(!isAllPass)

  const TurnIcon = TURN_ICON[turn.turn_type] ?? Bot
  const accent = TURN_ACCENT[turn.turn_type] ?? ""
  const turnLabel = TURN_LABEL[turn.turn_type]

  return (
    <div className={cn("rounded-lg border bg-card overflow-hidden", accent && `border-l-2 ${accent}`)}>
      {/* Card header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/20">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Turn {turn.turn_index + 1}</span>
          {turnLabel && (
            <span className={cn(
              "px-1.5 py-0.5 rounded text-[10px] font-medium",
              scoreBadgeClass(0.6), // subtle amber for non-response types
            )}>
              {turnLabel}
            </span>
          )}
        </div>
        {scores.length > 0 && (
          <div className="flex items-center gap-2">
            <span className={cn("text-xs font-semibold tabular-nums", scoreTextClass(avg))}>
              {avg.toFixed(2)}
            </span>
            <PassFailBadge score={avg} />
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="px-4 py-3 space-y-3">
        {/* User message */}
        <div className="flex items-start gap-2.5">
          <div className="size-6 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
            <User className="size-3.5 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-muted-foreground font-medium mb-1">User</p>
            <p className="text-sm">{turn.user_message}</p>
          </div>
        </div>

        {/* Agent message */}
        <div className="flex items-start gap-2.5">
          <div className="size-6 rounded-full border bg-card flex items-center justify-center shrink-0 mt-0.5">
            <TurnIcon className="size-3.5 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-muted-foreground font-medium mb-1">Agent</p>
            <p className="text-sm">{turn.agent_content}</p>
            {turn.tool_calls_made.length > 0 && (
              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                <Wrench className="size-3 text-muted-foreground shrink-0" />
                {turn.tool_calls_made.map((tc, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-muted text-muted-foreground"
                  >
                    {tc.function?.name ?? "unknown"}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Scores section */}
      {scores.length > 0 && (
        <div className="border-t">
          {isAllPass ? (
            /* Collapsed: all pass */
            <button
              className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-muted/30 transition-colors"
              onClick={() => setScoresOpen(v => !v)}
            >
              {scoresOpen ? (
                <ChevronDown className="size-3.5 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="size-3.5 text-muted-foreground shrink-0" />
              )}
              <CircleCheck className="size-3.5 text-emerald-500 shrink-0" />
              <span className="text-xs text-muted-foreground">
                All {scores.length} metrics passed
              </span>
            </button>
          ) : (
            /* Header: has issues */
            <div className="px-4 pt-2.5 pb-1">
              <p className="text-[11px] text-muted-foreground font-medium uppercase tracking-wide">
                Scores
              </p>
            </div>
          )}

          {scoresOpen && (
            <div className="px-4 pb-3 space-y-0.5">
              {scores.map(s => (
                <ScoreRow key={s.id} result={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
