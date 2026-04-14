/**
 * YAMLEditor — Monaco editor synced to the Zustand YAML store.
 *
 * Features:
 * - Monaco with YAML language, dark theme
 * - Debounced setYaml (500ms) on change
 * - External YAML changes (from ChatBuilder) reflected instantly
 * - Validation issues panel using Alert
 * - Cmd/Ctrl+S → save()
 */

import { useCallback, useEffect, useRef, useState } from "react"
import Editor, { type Monaco, type OnMount } from "@monaco-editor/react"
import { CheckCircle2, AlertCircle, AlertTriangle, Loader2, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useAgentStore } from "@/stores/agent.store"

export function YAMLEditor() {
  const {
    yamlContent,
    setYaml,
    save,
    validate,
    validationResult,
    isValidating,
    isSaving,
    isDirty,
  } = useAgentStore()

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const [editorReady, setEditorReady] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const externalUpdateRef = useRef(false)

  // Sync external YAML changes into Monaco
  useEffect(() => {
    const editor = editorRef.current
    if (!editor || !editorReady) return
    if (editor.getValue() !== yamlContent) {
      externalUpdateRef.current = true
      editor.setValue(yamlContent)
    }
  }, [yamlContent, editorReady])

  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor
      monacoRef.current = monaco
      setEditorReady(true)
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => save())
    },
    [save],
  )

  const handleChange = useCallback(
    (value: string | undefined) => {
      if (externalUpdateRef.current) {
        externalUpdateRef.current = false
        return
      }
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => setYaml(value ?? ""), 500)
    },
    [setYaml],
  )

  const errorCount = validationResult?.errors.length ?? 0
  const warningCount = validationResult?.warnings.length ?? 0
  const issues = validationResult
    ? [...(validationResult.errors ?? []), ...(validationResult.warnings ?? [])]
    : []

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">agent.yaml</span>
          {isDirty && <span className="size-1.5 rounded-full bg-amber-500" title="Unsaved" />}
        </div>

        <div className="flex items-center gap-2">
          {validationResult && (
            <>
              {errorCount > 0 ? (
                <Badge variant="destructive" className="gap-1">
                  <AlertCircle data-icon="inline-start" />
                  {errorCount} error{errorCount > 1 ? "s" : ""}
                </Badge>
              ) : warningCount > 0 ? (
                <Badge variant="outline" className="gap-1 text-amber-600 border-amber-500/50">
                  <AlertTriangle data-icon="inline-start" />
                  {warningCount} warning{warningCount > 1 ? "s" : ""}
                </Badge>
              ) : (
                <Badge variant="outline" className="gap-1 text-emerald-600 border-emerald-500/50">
                  <CheckCircle2 data-icon="inline-start" />
                  Valid
                </Badge>
              )}
            </>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={validate}
            disabled={isValidating}
            className="h-7 text-xs"
          >
            {isValidating && <Loader2 className="animate-spin" data-icon="inline-start" />}
            Validate
          </Button>

          <Button
            size="sm"
            onClick={save}
            disabled={isSaving || !isDirty}
            className="h-7 text-xs"
          >
            {isSaving ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            Save
          </Button>
        </div>
      </div>

      <Separator />

      {/* Monaco */}
      <div className="flex-1 overflow-hidden">
        <Editor
          language="yaml"
          value={yamlContent}
          onChange={handleChange}
          onMount={handleMount}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineHeight: 20,
            fontFamily: '"JetBrains Mono", "Fira Code", monospace',
            scrollBeyondLastLine: false,
            padding: { top: 12, bottom: 12 },
            wordWrap: "on",
            tabSize: 2,
            insertSpaces: true,
            renderLineHighlight: "gutter",
            smoothScrolling: true,
            cursorBlinking: "smooth",
          }}
        />
      </div>

      {/* Validation issues */}
      {issues.length > 0 && (
        <>
          <Separator />
          <ScrollArea className="max-h-36">
            <div className="flex flex-col gap-1 p-2">
              {issues.map((issue, i) => (
                <Alert
                  key={i}
                  variant={issue.severity === "error" ? "destructive" : "default"}
                  className="py-1 px-2"
                >
                  {issue.severity === "error" ? (
                    <AlertCircle className="size-3.5" />
                  ) : (
                    <AlertTriangle className="size-3.5" />
                  )}
                  <AlertDescription className="text-[11px]">
                    {issue.path && (
                      <span className="font-mono text-muted-foreground mr-1">{issue.path}</span>
                    )}
                    {issue.message}
                  </AlertDescription>
                </Alert>
              ))}
            </div>
          </ScrollArea>
        </>
      )}
    </div>
  )
}
