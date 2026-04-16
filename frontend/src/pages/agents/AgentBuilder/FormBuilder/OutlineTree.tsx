/**
 * OutlineTree — hierarchical tree of the agent schema.
 *
 * Renders top-level sections (persona, models, tools, conditions, etc.) and
 * drills into nested items (goals → slots/sequences/rules). Click a node to
 * select it; the right pane (NodeForm) renders the editor for that node.
 *
 * Mutations (add/delete/duplicate) are handled by handler props passed from
 * the parent FormBuilder so the YAML write path stays in one place.
 */

import { useEffect, useState } from "react"
import {
  AlertTriangle,
  Ban,
  Bot,
  ChevronDown,
  ChevronRight,
  Cpu,
  GitBranch,
  Layers,
  MessageSquare,
  MoreVertical,
  Plus,
  ShieldAlert,
  Sliders,
  Target,
  User,
  Wrench,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAgentStore, type ValidationResult } from "@/stores/agent.store"
import type { AgentSchema } from "@/types/agent"
import { joinPath, type Path } from "./yamlPath"

const STORAGE_KEY = "saras:builder:outline:expanded"

function loadExpanded(): Set<Path> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set([""])
    return new Set(JSON.parse(raw) as Path[])
  } catch {
    return new Set([""])
  }
}

function saveExpanded(set: Set<Path>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]))
  } catch { /* ignore */ }
}

// ── Validation helpers ────────────────────────────────────────────────────────

/** Count validation errors+warnings whose path starts with the given prefix. */
function countIssuesUnder(result: ValidationResult | null, prefix: Path): number {
  if (!result) return 0
  const issues = [...result.errors, ...result.warnings]
  return issues.filter(i => {
    if (!i.path) return false
    // Treat "" prefix as "all"
    if (!prefix) return true
    return i.path === prefix || i.path.startsWith(`${prefix}.`)
  }).length
}

// ── Tree node ─────────────────────────────────────────────────────────────────

interface NodeProps {
  label: string
  path: Path
  icon: React.ComponentType<{ className?: string }>
  count?: number
  hasChildren: boolean
  expanded: boolean
  selected: boolean
  depth: number
  issueCount: number
  onSelect: () => void
  onToggleExpand: () => void
  onAdd?: () => void
  onDelete?: () => void
  children?: React.ReactNode
}

function TreeNode({
  label, icon: Icon, count, hasChildren, expanded, selected, depth,
  issueCount, onSelect, onToggleExpand, onAdd, onDelete, children,
}: NodeProps) {
  const [hover, setHover] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 pr-1 rounded-sm cursor-pointer transition-colors",
          selected ? "bg-primary/10 text-primary" : "hover:bg-muted/60 text-foreground",
        )}
        style={{ paddingLeft: depth * 12 + 4 }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => { setHover(false); setMenuOpen(false) }}
        onClick={onSelect}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggleExpand() }}
            className="p-0.5 hover:bg-muted/40 rounded"
          >
            {expanded
              ? <ChevronDown className="size-3 text-muted-foreground" />
              : <ChevronRight className="size-3 text-muted-foreground" />
            }
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        <Icon className={cn("size-3.5 shrink-0", selected ? "text-primary" : "text-muted-foreground")} />

        <span className="flex-1 truncate text-xs py-1.5">{label}</span>

        {count !== undefined && count > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums px-1">
            {count}
          </span>
        )}

        {issueCount > 0 && (
          <span
            className="inline-flex items-center gap-0.5 text-[10px] text-amber-600"
            title={`${issueCount} validation ${issueCount === 1 ? "issue" : "issues"}`}
          >
            <AlertTriangle className="size-3" />
            {issueCount}
          </span>
        )}

        {/* Hover actions: + add child, kebab menu */}
        {(hover || menuOpen) && onAdd && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onAdd() }}
            className="p-0.5 hover:bg-muted/40 rounded opacity-70 hover:opacity-100"
            title="Add child"
          >
            <Plus className="size-3" />
          </button>
        )}
        {(hover || menuOpen) && onDelete && (
          <div className="relative">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(v => !v) }}
              className="p-0.5 hover:bg-muted/40 rounded opacity-70 hover:opacity-100"
              title="More"
            >
              <MoreVertical className="size-3" />
            </button>
            {menuOpen && (
              <div
                className="absolute top-full right-0 mt-1 z-10 min-w-[120px] rounded-md border border-border bg-popover shadow-md py-1"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => { onDelete(); setMenuOpen(false) }}
                  className="block w-full text-left px-3 py-1.5 text-xs hover:bg-muted text-destructive"
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {expanded && children}
    </div>
  )
}

// ── OutlineTree ───────────────────────────────────────────────────────────────

interface OutlineTreeProps {
  onAddChild: (parentPath: Path) => void
  onDelete: (path: Path) => void
}

export function OutlineTree({ onAddChild, onDelete }: OutlineTreeProps) {
  const { parsedSchema, selectedFormPath, setSelectedFormPath, validationResult } = useAgentStore()
  const [expanded, setExpanded] = useState<Set<Path>>(loadExpanded)

  useEffect(() => { saveExpanded(expanded) }, [expanded])

  const toggle = (path: Path) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  if (!parsedSchema) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center px-4">
        <Bot className="size-7 text-muted-foreground/40" />
        <p className="text-xs font-medium">No agent loaded</p>
        <p className="text-[11px] text-muted-foreground">
          Start in the Chat tab or write directly in YAML.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0.5 py-2">
      <RootSection
        schema={parsedSchema}
        expanded={expanded}
        toggle={toggle}
        selectedPath={selectedFormPath}
        onSelect={setSelectedFormPath}
        validationResult={validationResult}
        onAddChild={onAddChild}
        onDelete={onDelete}
      />
    </div>
  )
}

// ── Section renderers ─────────────────────────────────────────────────────────

interface SectionProps {
  schema: AgentSchema
  expanded: Set<Path>
  toggle: (p: Path) => void
  selectedPath: Path
  onSelect: (p: Path) => void
  validationResult: ValidationResult | null
  onAddChild: (parentPath: Path) => void
  onDelete: (path: Path) => void
}

function RootSection(props: SectionProps) {
  const { schema, expanded, toggle, selectedPath, onSelect, validationResult, onAddChild, onDelete } = props
  const rootExpanded = expanded.has("")

  return (
    <TreeNode
      label={schema.name || "Untitled Agent"}
      path=""
      icon={Bot}
      hasChildren
      expanded={rootExpanded}
      selected={selectedPath === ""}
      depth={0}
      issueCount={countIssuesUnder(validationResult, "")}
      onSelect={() => onSelect("")}
      onToggleExpand={() => toggle("")}
    >
      {/* Persona */}
      {schema.persona !== undefined && (
        <TreeNode
          label="persona"
          path="persona"
          icon={User}
          hasChildren={false}
          expanded={false}
          selected={selectedPath === "persona"}
          depth={1}
          issueCount={countIssuesUnder(validationResult, "persona")}
          onSelect={() => onSelect("persona")}
          onToggleExpand={() => {}}
          onDelete={() => onDelete("persona")}
        />
      )}

      {/* Models */}
      {schema.models !== undefined && (
        <TreeNode
          label="models"
          path="models"
          icon={Cpu}
          hasChildren={false}
          expanded={false}
          selected={selectedPath === "models"}
          depth={1}
          issueCount={countIssuesUnder(validationResult, "models")}
          onSelect={() => onSelect("models")}
          onToggleExpand={() => {}}
          onDelete={() => onDelete("models")}
        />
      )}

      {/* Tone */}
      {schema.tone !== undefined && (
        <TreeNode
          label="tone"
          path="tone"
          icon={MessageSquare}
          hasChildren={false}
          expanded={false}
          selected={selectedPath === "tone"}
          depth={1}
          issueCount={countIssuesUnder(validationResult, "tone")}
          onSelect={() => onSelect("tone")}
          onToggleExpand={() => {}}
          onDelete={() => onDelete("tone")}
        />
      )}

      {/* Global rules */}
      {schema.global_rules !== undefined && (
        <TreeNode
          label="global_rules"
          path="global_rules"
          icon={ShieldAlert}
          count={schema.global_rules.length}
          hasChildren={false}
          expanded={false}
          selected={selectedPath === "global_rules"}
          depth={1}
          issueCount={countIssuesUnder(validationResult, "global_rules")}
          onSelect={() => onSelect("global_rules")}
          onToggleExpand={() => {}}
          onDelete={() => onDelete("global_rules")}
        />
      )}

      {/* Tools */}
      {schema.tools !== undefined && (
        <CollectionSection
          label="tools"
          parentPath="tools"
          icon={Wrench}
          itemIcon={Wrench}
          items={schema.tools.map(t => ({ name: t.name }))}
          {...props}
        />
      )}

      {/* Conditions */}
      {schema.conditions !== undefined && (
        <ConditionsSection {...props} />
      )}

      {/* Handoffs */}
      {schema.handoffs !== undefined && (
        <CollectionSection
          label="handoffs"
          parentPath="handoffs"
          icon={GitBranch}
          itemIcon={GitBranch}
          items={schema.handoffs.map(h => ({ name: h.name }))}
          {...props}
        />
      )}

      {/* Interrupts */}
      {schema.interrupt_triggers !== undefined && (
        <CollectionSection
          label="interrupt_triggers"
          parentPath="interrupt_triggers"
          icon={AlertTriangle}
          itemIcon={AlertTriangle}
          items={schema.interrupt_triggers.map(t => ({ name: t.name }))}
          {...props}
        />
      )}

      {/* Out of scope */}
      {schema.out_of_scope !== undefined && (
        <TreeNode
          label="out_of_scope"
          path="out_of_scope"
          icon={Ban}
          count={schema.out_of_scope.length}
          hasChildren={false}
          expanded={false}
          selected={selectedPath === "out_of_scope"}
          depth={1}
          issueCount={countIssuesUnder(validationResult, "out_of_scope")}
          onSelect={() => onSelect("out_of_scope")}
          onToggleExpand={() => {}}
          onDelete={() => onDelete("out_of_scope")}
        />
      )}

      {/* Sub-agents */}
      {schema.sub_agents !== undefined && (
        <CollectionSection
          label="sub_agents"
          parentPath="sub_agents"
          icon={Layers}
          itemIcon={Layers}
          items={schema.sub_agents.map(s => ({ name: s.name }))}
          {...props}
        />
      )}

      {/* Add section (when missing) */}
      <AddSectionMenu schema={schema} onAdd={onAddChild} />
    </TreeNode>
  )
}

// ── Generic collection section (handoffs, interrupts, sub-agents, tools) ──────

interface CollectionSectionProps extends SectionProps {
  label: string
  parentPath: Path
  icon: React.ComponentType<{ className?: string }>
  itemIcon: React.ComponentType<{ className?: string }>
  items: Array<{ name: string }>
}

function CollectionSection(props: CollectionSectionProps) {
  const { label, parentPath, icon, itemIcon, items, expanded, toggle, selectedPath,
    onSelect, validationResult, onAddChild, onDelete } = props
  const isExpanded = expanded.has(parentPath)

  return (
    <TreeNode
      label={label}
      path={parentPath}
      icon={icon}
      count={items.length}
      hasChildren={items.length > 0}
      expanded={isExpanded}
      selected={selectedPath === parentPath}
      depth={1}
      issueCount={countIssuesUnder(validationResult, parentPath)}
      onSelect={() => onSelect(parentPath)}
      onToggleExpand={() => toggle(parentPath)}
      onAdd={() => onAddChild(parentPath)}
    >
      {items.map((item, i) => {
        const itemPath = `${parentPath}[${i}]`
        return (
          <TreeNode
            key={itemPath}
            label={item.name || `(unnamed ${label})`}
            path={itemPath}
            icon={itemIcon}
            hasChildren={false}
            expanded={false}
            selected={selectedPath === itemPath}
            depth={2}
            issueCount={countIssuesUnder(validationResult, itemPath)}
            onSelect={() => onSelect(itemPath)}
            onToggleExpand={() => {}}
            onDelete={() => onDelete(itemPath)}
          />
        )
      })}
    </TreeNode>
  )
}

// ── Conditions section (special: nested goals → slots/sequences/rules) ───────

function ConditionsSection(props: SectionProps) {
  const { schema, expanded, toggle, selectedPath, onSelect, validationResult,
    onAddChild, onDelete } = props
  const conditions = schema.conditions ?? []
  const isExpanded = expanded.has("conditions")

  return (
    <TreeNode
      label="conditions"
      path="conditions"
      icon={GitBranch}
      count={conditions.length}
      hasChildren={conditions.length > 0}
      expanded={isExpanded}
      selected={selectedPath === "conditions"}
      depth={1}
      issueCount={countIssuesUnder(validationResult, "conditions")}
      onSelect={() => onSelect("conditions")}
      onToggleExpand={() => toggle("conditions")}
      onAdd={() => onAddChild("conditions")}
    >
      {conditions.map((cond, ci) => {
        const condPath = `conditions[${ci}]`
        const condExpanded = expanded.has(condPath)
        const goals = cond.goals ?? []

        return (
          <TreeNode
            key={condPath}
            label={cond.name || "(unnamed condition)"}
            path={condPath}
            icon={GitBranch}
            count={goals.length}
            hasChildren={goals.length > 0}
            expanded={condExpanded}
            selected={selectedPath === condPath}
            depth={2}
            issueCount={countIssuesUnder(validationResult, condPath)}
            onSelect={() => onSelect(condPath)}
            onToggleExpand={() => toggle(condPath)}
            onAdd={() => onAddChild(joinPath(condPath, "goals"))}
            onDelete={() => onDelete(condPath)}
          >
            {goals.map((goal, gi) => {
              const goalPath = `${condPath}.goals[${gi}]`
              const goalExpanded = expanded.has(goalPath)
              const slots = goal.slots ?? []
              const sequences = goal.sequences ?? []
              const rules = goal.rules ?? []
              const hasGoalChildren = slots.length > 0 || sequences.length > 0 || rules.length > 0 || (goal.tools?.length ?? 0) > 0

              return (
                <TreeNode
                  key={goalPath}
                  label={goal.name || "(unnamed goal)"}
                  path={goalPath}
                  icon={Target}
                  hasChildren={hasGoalChildren}
                  expanded={goalExpanded}
                  selected={selectedPath === goalPath}
                  depth={3}
                  issueCount={countIssuesUnder(validationResult, goalPath)}
                  onSelect={() => onSelect(goalPath)}
                  onToggleExpand={() => toggle(goalPath)}
                  onDelete={() => onDelete(goalPath)}
                >
                  {/* Slots */}
                  {goal.slots !== undefined && (
                    <TreeNode
                      label="slots"
                      path={`${goalPath}.slots`}
                      icon={Sliders}
                      count={slots.length}
                      hasChildren={slots.length > 0}
                      expanded={expanded.has(`${goalPath}.slots`)}
                      selected={selectedPath === `${goalPath}.slots`}
                      depth={4}
                      issueCount={countIssuesUnder(validationResult, `${goalPath}.slots`)}
                      onSelect={() => onSelect(`${goalPath}.slots`)}
                      onToggleExpand={() => toggle(`${goalPath}.slots`)}
                      onAdd={() => onAddChild(`${goalPath}.slots`)}
                    >
                      {slots.map((slot, si) => {
                        const slotPath = `${goalPath}.slots[${si}]`
                        return (
                          <TreeNode
                            key={slotPath}
                            label={slot.name || "(unnamed slot)"}
                            path={slotPath}
                            icon={Sliders}
                            hasChildren={false}
                            expanded={false}
                            selected={selectedPath === slotPath}
                            depth={5}
                            issueCount={countIssuesUnder(validationResult, slotPath)}
                            onSelect={() => onSelect(slotPath)}
                            onToggleExpand={() => {}}
                            onDelete={() => onDelete(slotPath)}
                          />
                        )
                      })}
                    </TreeNode>
                  )}

                  {/* Sequences */}
                  {goal.sequences !== undefined && (
                    <TreeNode
                      label="sequences"
                      path={`${goalPath}.sequences`}
                      icon={Layers}
                      count={sequences.length}
                      hasChildren={sequences.length > 0}
                      expanded={expanded.has(`${goalPath}.sequences`)}
                      selected={selectedPath === `${goalPath}.sequences`}
                      depth={4}
                      issueCount={countIssuesUnder(validationResult, `${goalPath}.sequences`)}
                      onSelect={() => onSelect(`${goalPath}.sequences`)}
                      onToggleExpand={() => toggle(`${goalPath}.sequences`)}
                      onAdd={() => onAddChild(`${goalPath}.sequences`)}
                    >
                      {sequences.map((seq, si) => {
                        const seqPath = `${goalPath}.sequences[${si}]`
                        return (
                          <TreeNode
                            key={seqPath}
                            label={seq.name || "(unnamed sequence)"}
                            path={seqPath}
                            icon={Layers}
                            hasChildren={false}
                            expanded={false}
                            selected={selectedPath === seqPath}
                            depth={5}
                            issueCount={countIssuesUnder(validationResult, seqPath)}
                            onSelect={() => onSelect(seqPath)}
                            onToggleExpand={() => {}}
                            onDelete={() => onDelete(seqPath)}
                          />
                        )
                      })}
                    </TreeNode>
                  )}

                  {/* Rules */}
                  {goal.rules !== undefined && goal.rules.length > 0 && (
                    <TreeNode
                      label="rules"
                      path={`${goalPath}.rules`}
                      icon={ShieldAlert}
                      count={rules.length}
                      hasChildren={false}
                      expanded={false}
                      selected={selectedPath === `${goalPath}.rules`}
                      depth={4}
                      issueCount={countIssuesUnder(validationResult, `${goalPath}.rules`)}
                      onSelect={() => onSelect(`${goalPath}.rules`)}
                      onToggleExpand={() => {}}
                    />
                  )}
                </TreeNode>
              )
            })}
          </TreeNode>
        )
      })}
    </TreeNode>
  )
}

// ── Add-section menu (for top-level sections that aren't set yet) ─────────────

function AddSectionMenu({
  schema, onAdd,
}: {
  schema: AgentSchema
  onAdd: (parentPath: Path) => void
}) {
  const [open, setOpen] = useState(false)

  const missing: Array<{ key: string; label: string }> = []
  if (schema.persona === undefined) missing.push({ key: "persona", label: "Persona" })
  if (schema.tone === undefined) missing.push({ key: "tone", label: "Tone" })
  if (schema.models === undefined) missing.push({ key: "models", label: "Models" })
  if (schema.global_rules === undefined) missing.push({ key: "global_rules", label: "Global rules" })
  if (schema.tools === undefined) missing.push({ key: "tools", label: "Tools" })
  if (schema.conditions === undefined) missing.push({ key: "conditions", label: "Conditions" })
  if (schema.handoffs === undefined) missing.push({ key: "handoffs", label: "Handoffs" })
  if (schema.interrupt_triggers === undefined) missing.push({ key: "interrupt_triggers", label: "Interrupt triggers" })
  if (schema.out_of_scope === undefined) missing.push({ key: "out_of_scope", label: "Out of scope" })
  if (schema.sub_agents === undefined) missing.push({ key: "sub_agents", label: "Sub-agents" })

  if (missing.length === 0) return null

  return (
    <div className="relative" style={{ paddingLeft: 16 }}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground rounded-sm hover:bg-muted/40"
      >
        <Plus className="size-3" />
        Add section
      </button>
      {open && (
        <div className="absolute top-full left-4 z-10 min-w-[160px] rounded-md border border-border bg-popover shadow-md py-1">
          {missing.map(m => (
            <button
              key={m.key}
              type="button"
              onClick={() => { onAdd(m.key); setOpen(false) }}
              className="block w-full text-left px-3 py-1.5 text-xs hover:bg-muted"
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
