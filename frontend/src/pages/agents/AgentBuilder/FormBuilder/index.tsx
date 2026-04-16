/**
 * FormBuilder — outline tree (left) + dynamic per-node form (right).
 *
 * Replaces the previous flat block-list UI. Provides full schema coverage:
 * every field in the agent YAML is editable via the form, including goals,
 * slots, sequences, models, sub-agents, and tool inputs/handlers.
 *
 * YAML remains the source of truth. Form mutations flow:
 *   form input → updated parsedSchema → js-yaml.dump → store.setYaml → re-derive
 *
 * Switching to the YAML tab shows the same edits round-tripped through YAML.
 */

import { useEffect } from "react"
import * as yaml from "js-yaml"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { useAgentStore } from "@/stores/agent.store"
import type { AgentSchema, AgentTool, Condition, Goal, Handoff, InterruptTrigger, Slot, Sequence, SubAgent } from "@/types/agent"
import { OutlineTree } from "./OutlineTree"
import { NodeForm } from "./NodeForm"
import { appendArrayItem, deleteNodeAtPath, getNodeAtPath, setNodeAtPath, type Path } from "./yamlPath"

const SELECTED_PATH_KEY = "saras:builder:selectedPath"

// ── Default values for inserted nodes ─────────────────────────────────────────

function defaultForArrayPath(arrayPath: Path): unknown {
  if (arrayPath === "tools") {
    const t: AgentTool = { name: "New Tool", type: "LookupTool", description: "" }
    return t
  }
  if (arrayPath === "conditions") {
    const c: Condition = { name: "New Condition", description: "", goals: [] }
    return c
  }
  if (arrayPath === "handoffs") {
    const h: Handoff = { name: "New Handoff", description: "", target: "Human Support Queue" }
    return h
  }
  if (arrayPath === "interrupt_triggers") {
    const i: InterruptTrigger = { name: "New Trigger", description: "" }
    return i
  }
  if (arrayPath === "sub_agents") {
    const s: SubAgent = { name: "New Sub-agent" }
    return s
  }
  if (arrayPath.endsWith(".goals")) {
    const g: Goal = { name: "New Goal", description: "" }
    return g
  }
  if (arrayPath.endsWith(".slots")) {
    const s: Slot = { name: "new_slot", description: "", required: false }
    return s
  }
  if (arrayPath.endsWith(".sequences")) {
    const s: Sequence = { name: "New Sequence", steps: [] }
    return s
  }
  if (arrayPath.endsWith(".rules")) {
    return ""
  }
  return null
}

function defaultForTopLevelKey(key: string): unknown {
  switch (key) {
    case "persona": return ""
    case "tone": return ""
    case "models": return { primary: "" }
    case "global_rules": return []
    case "tools": return []
    case "conditions": return []
    case "handoffs": return []
    case "interrupt_triggers": return []
    case "out_of_scope": return []
    case "sub_agents": return []
    default: return null
  }
}

// ── FormBuilder ───────────────────────────────────────────────────────────────

export function FormBuilder() {
  const {
    parsedSchema,
    setYaml,
    yamlContent,
    selectedFormPath,
    setSelectedFormPath,
  } = useAgentStore()

  // Restore selection from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(SELECTED_PATH_KEY)
      if (saved !== null && saved !== selectedFormPath) {
        setSelectedFormPath(saved)
      }
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Persist selection on change
  useEffect(() => {
    try {
      localStorage.setItem(SELECTED_PATH_KEY, selectedFormPath)
    } catch { /* ignore */ }
  }, [selectedFormPath])

  const handleSchemaChange = (updated: AgentSchema) => {
    try {
      const raw = yaml.load(yamlContent) as Record<string, unknown> | null
      const newRaw = { ...(raw ?? {}), agent: updated }
      setYaml(yaml.dump(newRaw, { lineWidth: 100 }))
    } catch {
      setYaml(yaml.dump({ agent: updated }, { lineWidth: 100 }))
    }
  }

  const handleAddChild = (parentPath: Path) => {
    if (!parsedSchema) return

    // Top-level missing section: parentPath is just a key like "persona"
    const isTopLevelKey = !parentPath.includes(".") && !parentPath.includes("[")
    const isExistingArray = Array.isArray(getNodeAtPath(parsedSchema, parentPath))

    if (isTopLevelKey && !isExistingArray) {
      // Adding a new top-level section
      const value = defaultForTopLevelKey(parentPath)
      if (value === null) return
      const updated = setNodeAtPath(parsedSchema, parentPath, value)
      handleSchemaChange(updated)
      // Select the new section
      setSelectedFormPath(parentPath)
      return
    }

    // Append to an existing array
    const item = defaultForArrayPath(parentPath)
    if (item === null) return
    const [updated, newPath] = appendArrayItem(parsedSchema, parentPath, item)
    handleSchemaChange(updated)
    setSelectedFormPath(newPath)
  }

  const handleDelete = (path: Path) => {
    if (!parsedSchema) return
    const updated = deleteNodeAtPath(parsedSchema, path)
    handleSchemaChange(updated)
    // Move selection to parent if the deleted node was selected
    if (selectedFormPath === path || selectedFormPath.startsWith(`${path}.`) || selectedFormPath.startsWith(`${path}[`)) {
      const parent = path.includes(".")
        ? path.slice(0, path.lastIndexOf("."))
        : path.includes("[")
          ? path.slice(0, path.indexOf("["))
          : ""
      setSelectedFormPath(parent)
    }
  }

  return (
    <ResizablePanelGroup orientation="horizontal" className="h-full">
      {/* Outline */}
      <ResizablePanel defaultSize="35%" minSize="20%" className="flex flex-col overflow-hidden">
        <div className="border-b border-border px-3 py-2 shrink-0">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            Outline
          </p>
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          <OutlineTree onAddChild={handleAddChild} onDelete={handleDelete} />
        </div>
      </ResizablePanel>

      <ResizableHandle withHandle />

      {/* Form */}
      <ResizablePanel defaultSize="65%" minSize="50%" className="overflow-hidden">
        {parsedSchema ? (
          <NodeForm
            schema={parsedSchema}
            selectedPath={selectedFormPath}
            onChange={handleSchemaChange}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full p-8 text-center">
            <p className="text-sm font-medium">No agent loaded</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-xs">
              Start in the Chat tab to scaffold an agent, or write directly in the YAML tab.
            </p>
          </div>
        )}
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
