/**
 * BuilderLayout — top-level agent builder page.
 *
 * Uses ResizablePanelGroup to split: left pane (active tab) + right YAML side-pane.
 * Tab switcher in header uses shadcn Tabs (line variant).
 */

import { useEffect } from "react"
import { useParams, Link } from "react-router-dom"
import { MessageSquare, LayoutGrid, GitBranch, FileCode2, Play, ChevronLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable"
import { useAgentStore } from "@/stores/agent.store"
import { ChatBuilder } from "./ChatBuilder"
import { YAMLEditor } from "./YAMLEditor"
import { FormBuilder } from "./FormBuilder"
import { GraphBuilder } from "./GraphBuilder"

type Tab = "chat" | "form" | "graph" | "yaml"

export function BuilderLayout() {
  const { projectId = "", agentId } = useParams<{ projectId: string; agentId?: string }>()
  const { activeTab, setActiveTab, loadAgent, initNew, agentRecord, isSaving, isDirty } =
    useAgentStore()

  useEffect(() => {
    if (agentId) {
      loadAgent(projectId, agentId)
    } else {
      initNew(projectId)
    }
  }, [agentId, initNew, loadAgent, projectId])

  const agentName = agentRecord?.name ?? (agentId ? "Loading…" : "New Agent")
  const isYamlTab = activeTab === "yaml"

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex items-center justify-between gap-4 border-b border-border px-4 py-2 shrink-0">
        {/* Left: back + name */}
        <div className="flex items-center gap-2 min-w-0">
          <Button variant="ghost" size="icon" className="size-7 shrink-0" render={<Link to={`/projects/${projectId}/agents`} />}>
            <ChevronLeft />
          </Button>
          <span className="font-medium text-sm truncate">{agentName}</span>
          {agentRecord && (
            <span className="text-xs text-muted-foreground shrink-0">
              v{agentRecord.current_version}
            </span>
          )}
          {isDirty && (
            <Badge variant="outline" className="shrink-0 text-[10px]">
              unsaved
            </Badge>
          )}
        </div>

        {/* Center: tab switcher */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
          <TabsList variant="default">
            <TabsTrigger value="chat">
              <MessageSquare data-icon="inline-start" />
              Chat
            </TabsTrigger>
            <TabsTrigger value="form">
              <LayoutGrid data-icon="inline-start" />
              Form
            </TabsTrigger>
            <TabsTrigger value="graph">
              <GitBranch data-icon="inline-start" />
              Graph
            </TabsTrigger>
            <TabsTrigger value="yaml">
              <FileCode2 data-icon="inline-start" />
              YAML
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Right: actions */}
        <div className="flex items-center gap-2 shrink-0">
          {isSaving && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          {agentId && (
            <Button size="sm" render={<Link to={`/projects/${projectId}/agents/${agentId}/simulate`} />}>
              <Play data-icon="inline-start" />
              Simulate
            </Button>
          )}
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {isYamlTab ? (
          <YAMLEditor />
        ) : (
          <ResizablePanelGroup orientation="horizontal" className="h-full">
            {/* Primary pane */}
            <ResizablePanel defaultSize="60%" minSize="30%">
              <TabContent activeTab={activeTab as Tab} projectId={projectId} agentId={agentId} />
            </ResizablePanel>

            {/* YAML side panel */}
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize="40%" minSize="20%" className="hidden lg:flex flex-col">
              <div className="flex items-center gap-2 border-b border-border px-3 py-2 shrink-0">
                <FileCode2 className="size-3.5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground font-medium">Live YAML</span>
              </div>
              <div className="flex-1 overflow-hidden">
                <YAMLEditor />
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </div>
    </div>
  )
}

// ── Tab content router ─────────────────────────────────────────────────────────

function TabContent({
  activeTab,
  projectId,
  agentId,
}: {
  activeTab: Tab
  projectId: string
  agentId?: string
}) {
  switch (activeTab) {
    case "chat":
      return <ChatBuilder projectId={projectId} agentId={agentId} />
    case "form":
      return <FormBuilder />
    case "graph":
      return <GraphBuilder />
    default:
      return null
  }
}
