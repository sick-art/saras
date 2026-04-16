// TypeScript types for datasets and evals, mirroring backend Pydantic models.

// ── Datasets ──────────────────────────────────────────────────────────────────

export interface DatasetItem {
  id: string
  dataset_id: string
  input: ScriptedInput | SimulatedInput | Record<string, unknown>
  expected_output: ExpectedOutput | null
  source: "human" | "auto" | "llm_annotated"
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface ScriptedInput {
  turns: string[]
}

export interface SimulatedInput {
  scenario: SimulatedScenario
}

export interface SimulatedScenario {
  persona: string
  goal: string
  max_turns?: number
  stop_signal?: string | null
}

export interface ExpectedOutput {
  turns?: string[]
  tool_calls?: ExpectedToolCall[]
}

export interface ExpectedToolCall {
  turn: number
  tool_name: string
  required_args?: string[]
}

export interface Dataset {
  id: string
  project_id: string
  name: string
  description: string | null
  item_count: number
  created_at: string
}

export interface DatasetDetail extends Dataset {
  items: DatasetItem[]
}

// ── Eval suites ───────────────────────────────────────────────────────────────

export interface EvalSuite {
  id: string
  project_id: string
  name: string
  description: string | null
  agent_id: string | null
  metric_set_yaml: string
  run_count: number
  created_at: string
}

// ── Eval runs ─────────────────────────────────────────────────────────────────

export type EvalRunStatus = "pending" | "running" | "completed" | "failed"

export interface EvalRun {
  id: string
  suite_id: string
  dataset_id: string
  agent_id: string | null
  agent_version: string | null
  status: EvalRunStatus
  started_at: string | null
  ended_at: string | null
  summary: EvalRunSummary | null
  result_count: number
}

export interface EvalRunSummary {
  total_items: number
  metrics: Record<string, MetricSummary>
  error?: string
}

export interface MetricSummary {
  avg_score: number
  min_score: number
  max_score: number
  pass_rate: number
}

// ── Eval results ──────────────────────────────────────────────────────────────

export type EvalScope = "per_turn" | "whole_conversation" | "tool_call"

export interface EvalResult {
  id: string
  eval_run_id: string
  dataset_item_id: string
  metric_id: string
  score: number | null
  reasoning: string | null
  model_used: string | null
  turn_index: number | null
  scope: EvalScope
  created_at: string
}

export interface ItemResults {
  dataset_item_id: string
  conversation: ConversationSnapshot | null
  expected_output: ExpectedOutput | null
  scores: EvalResult[]
}

export interface ConversationSnapshot {
  item_id: string
  history: ConversationMessage[]
  turns: TurnRecord[]
  total_tokens: number
  total_cost_usd: number
  error?: string | null
}

export interface ConversationMessage {
  role: "user" | "assistant" | "system" | "tool"
  content: string
}

export interface TurnRecord {
  turn_index: number
  user_message: string
  agent_content: string
  turn_type: "response" | "slot_fill" | "interrupt" | "handoff"
  tool_calls_made: ToolCall[]
  router_decision: Record<string, unknown> | null
  input_tokens: number
  output_tokens: number
  cost_usd: number
}

export interface ToolCall {
  function?: {
    name: string
    arguments: string | Record<string, unknown>
  }
}

// ── Preset metrics ────────────────────────────────────────────────────────────

export type MetricType = "llm_judge" | "deterministic"
export type MetricScope = "per_turn" | "whole_conversation" | "tool_call"

export interface PresetMetric {
  key: string
  name: string
  type: MetricType
  scope: MetricScope
  description: string
}

// ── SSE events ────────────────────────────────────────────────────────────────

export type EvalProgressEvent =
  | { type: "progress"; completed: number; total: number }
  | { type: "item_done"; item_id: string; completed: number; total: number; scores: Record<string, number>; tokens: number; cost_usd: number }
  | { type: "complete"; summary: EvalRunSummary }
  | { type: "error"; message: string }

// ── Quick eval ──────────────────────────────────────────────────────────────

export interface QuickEvalRequest {
  dataset_id: string
  agent_id: string
  metrics?: string[]
}
