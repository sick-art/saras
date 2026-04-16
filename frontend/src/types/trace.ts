// TypeScript types mirroring the traces API response models.

export type RunStatus = "running" | "completed" | "failed" | "cancelled"
export type RunSource = "simulator" | "production" | "sdk"

export type SpanType =
  | "router_start"
  | "router_decision"
  | "router_parse_error"
  | "interrupt_triggered"
  | "handoff_triggered"
  | "slot_fill"
  | "llm_call_start"
  | "llm_call_end"
  | "tool_call"
  | "tool_result"
  | "tool_error"
  | "tool_loop_exceeded"
  | "turn_complete"
  | string // forward-compat for new span types

export interface LLMMessage {
  role: "system" | "user" | "assistant" | "tool"
  content: string | unknown[] | null
  // assistant messages with tool calls
  tool_calls?: Array<{
    id: string
    type: "function"
    function: { name: string; arguments: string }
  }>
  // tool result messages
  tool_call_id?: string
}

export interface LLMToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface SpanPayload {
  // llm_call_start
  messages?: LLMMessage[]       // full prompt sent to the model
  n_messages?: number
  // llm_call_end
  model?: string
  input_tokens?: number
  output_tokens?: number
  stop_reason?: string
  iteration?: number
  output?: string               // text response from the model
  tool_calls?: LLMToolCall[]    // tool calls requested by the model
  // tool_call / tool_result
  tool?: string
  arguments?: Record<string, unknown>
  result_preview?: string
  // router_decision
  decision?: Record<string, unknown>
  prompt?: string               // routing prompt sent to router
  system_prompt?: string        // router / primary-model system prompt
  // router_parse_error / tool_error
  error?: string
  raw_output?: string
  // tool_loop_exceeded
  iterations?: number
  last_tool_calls?: string[]
  // slot_fill
  slot_name?: string
  // turn_complete
  duration_ms?: number
  estimated_cost_usd?: number
  total_input_tokens?: number
  total_output_tokens?: number
  content?: string              // final assistant output (all turn types)
  turn_type?: string            // "response" | "slot_fill" | "interrupt" | "handoff"
  // router_decision
  user_message?: string         // raw user input for this turn
  // generic
  [key: string]: unknown
}

export interface Span {
  id: string
  run_id: string
  parent_span_id: string | null
  name: string
  type: SpanType
  started_at: string   // ISO-8601
  ended_at: string | null
  duration_ms: number | null
  payload: SpanPayload | null
}

export interface RunSummary {
  id: string
  agent_id: string | null
  agent_name: string | null
  agent_version: string | null
  session_id: string | null
  status: RunStatus
  source: RunSource
  started_at: string
  ended_at: string | null
  total_tokens: number
  total_cost_usd: number
  span_count: number | null
}

export interface RunDetail extends RunSummary {
  spans: Span[]
}

export interface RunListResponse {
  runs: RunSummary[]
  total: number
  limit: number
  offset: number
}

// Sessions ──────────────────────────────────────────────────────────────────

export interface SessionSummary {
  session_id: string
  agent_id: string | null
  agent_name: string | null
  agent_version: string | null
  run_count: number
  started_at: string
  ended_at: string | null
  total_tokens: number
  total_cost_usd: number
  status: RunStatus
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
  limit: number
  offset: number
}

export interface SessionDetail {
  session_id: string
  agent_name: string | null
  agent_version: string | null
  runs: RunDetail[]
}

// Analytics ─────────────────────────────────────────────────────────────────

export interface CostDataPoint {
  date: string        // "YYYY-MM-DD"
  cost_usd: number
  run_count: number
}

export interface LatencyStats {
  p50: number
  p95: number
  mean: number
  total_runs: number
}

export interface ModelUsage {
  model: string
  run_count: number
  total_tokens: number
  total_cost_usd: number
}

export interface ErrorRates {
  total: number
  errors: number
  error_rate_pct: number
}

export interface SpanTypeBreakdown {
  span_type: string
  count: number
  avg_duration_ms: number
}

export interface AnalyticsSummary {
  cost_over_time: CostDataPoint[]
  latency: LatencyStats
  models: ModelUsage[]
  errors: ErrorRates
  span_types: SpanTypeBreakdown[]
}
