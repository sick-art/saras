/**
 * ToolMultiSelect — multi-select chip input pulling tool names from the agent schema.
 *
 * Allows users to reference tools by name in goal.tools[] without typos. Shows
 * defined tool names as suggestions; warns if a referenced tool doesn't exist.
 */

import { Plus, X } from "lucide-react"
import { useState } from "react"
import { useAgentStore } from "@/stores/agent.store"
import { cn } from "@/lib/utils"

interface Props {
  label?: string
  hint?: string
  selected: string[]
  onChange: (selected: string[]) => void
}

export function ToolMultiSelect({ label, hint, selected, onChange }: Props) {
  const { parsedSchema } = useAgentStore()
  const definedTools = parsedSchema?.tools?.map(t => t.name) ?? []
  const available = definedTools.filter(name => !selected.includes(name))
  const [pickerOpen, setPickerOpen] = useState(false)

  const remove = (name: string) => onChange(selected.filter(n => n !== name))
  const add = (name: string) => {
    onChange([...selected, name])
    setPickerOpen(false)
  }

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-xs font-medium text-foreground">{label}</label>
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      <div className="flex flex-wrap gap-1.5 items-center">
        {selected.map(name => {
          const isDefined = definedTools.includes(name)
          return (
            <span
              key={name}
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs",
                isDefined
                  ? "bg-muted text-foreground"
                  : "bg-red-500/10 text-red-600",
              )}
              title={isDefined ? "" : "This tool is not defined at the agent level"}
            >
              {name}
              <button
                type="button"
                onClick={() => remove(name)}
                className="hover:text-foreground/60"
                aria-label={`Remove ${name}`}
              >
                <X className="size-3" />
              </button>
            </span>
          )
        })}

        {/* Picker */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setPickerOpen(v => !v)}
            disabled={available.length === 0}
            className="inline-flex items-center gap-1 rounded-md border border-dashed border-input px-2 py-1 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="size-3" />
            Add tool
          </button>
          {pickerOpen && available.length > 0 && (
            <div className="absolute top-full left-0 mt-1 z-10 min-w-[160px] rounded-md border border-border bg-popover shadow-md py-1">
              {available.map(name => (
                <button
                  key={name}
                  type="button"
                  onClick={() => add(name)}
                  className="block w-full text-left px-3 py-1.5 text-xs hover:bg-muted"
                >
                  {name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {definedTools.length === 0 && (
        <p className="text-[11px] text-muted-foreground italic">
          No tools defined yet. Add tools at the agent level first.
        </p>
      )}
    </div>
  )
}
