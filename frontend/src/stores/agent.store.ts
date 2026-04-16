/**
 * Zustand store for the Agent Builder.
 *
 * Design:
 * - yamlContent is the single source of truth (a string).
 * - parsedSchema is always derived from yamlContent — never set directly.
 * - validationResult is populated by calling validate() against the backend.
 * - isDirty tracks whether yamlContent differs from the last saved version.
 * - savedYaml holds the last DB-persisted YAML for dirty comparison.
 *
 * The store does NOT own HTTP calls to the builder/chat SSE endpoint —
 * that lives in ChatBuilder.tsx. applyDiff() and setYaml() are the two
 * entry points from streaming results.
 */

import { create } from "zustand"
import { api } from "@/lib/api"
import type { AgentSchema, AgentRecord } from "@/types/agent"

// We use a lightweight YAML parser for client-side schema derivation.
// js-yaml is already pulled in transitively; if not available, we skip parsing.
let jsyaml: { load: (s: string) => unknown } | null = null
try {
  // dynamic import used at call-site to avoid hard dep at module load
} catch {
  // no-op
}

async function loadYaml() {
  if (!jsyaml) {
    const mod = await import("js-yaml").catch(() => null)
    if (mod) jsyaml = mod
  }
  return jsyaml
}

// ── Validation types (mirror of backend ValidationResult.to_dict()) ───────────

export interface ValidationIssue {
  severity: "error" | "warning" | "info"
  code: string
  message: string
  path: string | null
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  infos: ValidationIssue[]
}

// ── Store shape ────────────────────────────────────────────────────────────────

export interface AgentStoreState {
  // Identity
  projectId: string | null
  agentId: string | null
  agentRecord: AgentRecord | null

  // Content
  yamlContent: string
  parsedSchema: AgentSchema | null

  // Validation
  validationResult: ValidationResult | null
  isValidating: boolean

  // Save state
  isDirty: boolean
  isSaving: boolean
  savedYaml: string

  // Active builder tab
  activeTab: "chat" | "form" | "graph" | "yaml"

  // Currently selected node path in the Form tab outline tree.
  // "" = agent root; "tools[0]" = first tool; "conditions[0].goals[1].slots[0]" = nested.
  selectedFormPath: string
}

export interface AgentStoreActions {
  /** Load an existing agent from the API into the store. */
  loadAgent: (projectId: string, agentId: string) => Promise<void>

  /** Initialise store for a new agent (no DB record yet). */
  initNew: (projectId: string) => void

  /** Set raw YAML string and re-derive parsedSchema. */
  setYaml: (yaml: string) => void

  /**
   * Apply a unified diff to yamlContent.
   * Falls back to setYaml(updatedYaml) if patch application fails.
   */
  applyDiff: (diff: string, updatedYaml: string) => void

  /** Persist current YAML to the backend via PATCH. */
  save: () => Promise<void>

  /** Run server-side validation and populate validationResult. */
  validate: () => Promise<void>

  /** Switch active builder tab. */
  setActiveTab: (tab: AgentStoreState["activeTab"]) => void

  /** Set the selected node path in the Form tab outline tree. */
  setSelectedFormPath: (path: string) => void

  /** Reset to initial state. */
  reset: () => void
}

export type AgentStore = AgentStoreState & AgentStoreActions

// ── Initial state ──────────────────────────────────────────────────────────────

const INITIAL_STATE: AgentStoreState = {
  projectId: null,
  agentId: null,
  agentRecord: null,
  yamlContent: "",
  parsedSchema: null,
  validationResult: null,
  isValidating: false,
  isDirty: false,
  isSaving: false,
  savedYaml: "",
  activeTab: "chat",
  selectedFormPath: "",
}

// ── Helpers ────────────────────────────────────────────────────────────────────

async function parseSchema(yamlStr: string): Promise<AgentSchema | null> {
  if (!yamlStr.trim()) return null
  try {
    const lib = await loadYaml()
    if (!lib) return null
    const raw = lib.load(yamlStr) as Record<string, unknown>
    return (raw?.agent as AgentSchema) ?? null
  } catch {
    return null
  }
}

// ── Store ──────────────────────────────────────────────────────────────────────

export const useAgentStore = create<AgentStore>()((set, get) => ({
  ...INITIAL_STATE,

  loadAgent: async (projectId, agentId) => {
    const record = await api.get<AgentRecord>(`/projects/${projectId}/agents/${agentId}`)
    const parsed = await parseSchema(record.yaml_content)
    set({
      projectId,
      agentId,
      agentRecord: record,
      yamlContent: record.yaml_content,
      parsedSchema: parsed,
      savedYaml: record.yaml_content,
      isDirty: false,
    })
  },

  initNew: (projectId) => {
    set({
      ...INITIAL_STATE,
      projectId,
      agentId: null,
      agentRecord: null,
      activeTab: "chat",
    })
  },

  setYaml: (yaml) => {
    const { savedYaml } = get()
    parseSchema(yaml).then((parsed) => {
      set({ parsedSchema: parsed })
    })
    set({
      yamlContent: yaml,
      isDirty: yaml !== savedYaml,
    })
  },

  applyDiff: (_diff, updatedYaml) => {
    // We receive the full updated YAML from the builder endpoint alongside the diff.
    // The diff is kept for display purposes; we always apply the full updated YAML.
    get().setYaml(updatedYaml)
  },

  save: async () => {
    const { projectId, agentId, yamlContent, parsedSchema, isSaving } = get()
    if (!projectId || isSaving) return

    set({ isSaving: true })
    try {
      if (agentId) {
        // Update existing agent
        const updated = await api.patch<AgentRecord>(
          `/projects/${projectId}/agents/${agentId}`,
          { yaml_content: yamlContent, name: parsedSchema?.name ?? "Untitled Agent" },
        )
        set({
          agentRecord: updated,
          savedYaml: yamlContent,
          isDirty: false,
        })
      } else {
        // Create new agent
        const created = await api.post<AgentRecord>(`/projects/${projectId}/agents`, {
          name: parsedSchema?.name ?? "Untitled Agent",
          description: parsedSchema?.description ?? null,
          yaml_content: yamlContent,
        })
        set({
          agentId: created.id,
          agentRecord: created,
          savedYaml: yamlContent,
          isDirty: false,
        })
      }
    } finally {
      set({ isSaving: false })
    }
  },

  validate: async () => {
    const { projectId, agentId, yamlContent, isValidating } = get()
    if (!projectId || isValidating) return

    set({ isValidating: true })
    try {
      const path = agentId
        ? `/projects/${projectId}/agents/${agentId}/validate`
        : `/projects/${projectId}/agents/validate`
      const result = await api.post<ValidationResult>(path, {
        yaml_content: yamlContent,
      })
      set({ validationResult: result })
    } catch {
      // Non-critical — keep existing result
    } finally {
      set({ isValidating: false })
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),

  setSelectedFormPath: (path) => set({ selectedFormPath: path }),

  reset: () => set(INITIAL_STATE),
}))
