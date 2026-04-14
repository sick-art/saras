// TypeScript types mirroring the Saras YAML agent schema.
// YAML is the source of truth; these types are used for UI rendering and validation.

export interface AgentModels {
  primary: string
  router?: string
  judge?: string
  fallback?: string
}

export interface ToolInput {
  name: string
  description: string
  required: boolean
}

export type ToolType = "LookupTool" | "KnowledgeTool" | "ActionTool"

export interface AgentTool {
  name: string
  type: ToolType
  description: string
  endpoint?: string
  auth?: string
  source?: string
  collection?: string
  confirmation_required?: boolean
  inputs?: ToolInput[]
  on_failure?: string
  on_empty_result?: string
}

export interface Slot {
  name: string
  description: string
  required: boolean
  ask_if_missing?: string
}

export interface Sequence {
  name: string
  description?: string
  steps: string[]
}

export interface Goal {
  name: string
  description: string
  tone?: string
  slots?: Slot[]
  sequences?: Sequence[]
  rules?: string[]
  tools?: string[] // names referencing agent-level tools
}

export interface Condition {
  name: string
  description: string
  goals: Goal[]
}

export interface Handoff {
  name: string
  description: string
  target: string // agent name or "Human Support Queue"
  context_to_pass?: string
}

export interface InterruptTrigger {
  name: string
  description: string
  action?: string
}

export interface SubAgent {
  name: string
  ref?: string // path to YAML file
  inline?: Partial<AgentSchema>
}

export interface AgentSchema {
  name: string
  version?: string
  description?: string
  models?: AgentModels
  persona?: string
  tone?: string
  global_rules?: string[]
  interrupt_triggers?: InterruptTrigger[]
  out_of_scope?: string[]
  handoffs?: Handoff[]
  tools?: AgentTool[]
  conditions?: Condition[]
  sub_agents?: SubAgent[]
}

// API response types
export interface AgentRecord {
  id: string
  project_id: string
  name: string
  description: string | null
  yaml_content: string
  current_version: string
  is_published: boolean
  created_at: string
  updated_at: string
}

export interface AgentVersionRecord {
  id: string
  agent_id: string
  version: string
  yaml_content: string
  change_summary: string | null
  created_at: string
}

export interface ProjectRecord {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}
