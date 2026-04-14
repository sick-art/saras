/**
 * ChatBuilder — conversational builder pane.
 *
 * Calls POST /builder/chat (streaming SSE).
 * Streams explanation as assistant message, then applies updated YAML to store.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Send, Loader2, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { useAgentStore } from "@/stores/agent.store"

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

interface Message {
  role: "user" | "assistant"
  content: string
  isStreaming?: boolean
  hasDiff?: boolean
}

const STARTER_PROMPTS = [
  "Create a customer support agent for an e-commerce store",
  "Add a slot to collect the user's order number",
  "Add a handoff to human support when the user is frustrated",
  "Add a condition for billing and payment questions",
]

interface ChatBuilderProps {
  projectId: string
  agentId?: string
}

export function ChatBuilder({ projectId, agentId }: ChatBuilderProps) {
  const { yamlContent, applyDiff, setActiveTab } = useAgentStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const sendMessage = useCallback(
    async (text: string) => {
      const userText = text.trim()
      if (!userText || isStreaming) return

      setInput("")
      const assistantIdx = messages.length + 1

      setMessages((prev) => [
        ...prev,
        { role: "user", content: userText },
        { role: "assistant", content: "", isStreaming: true },
      ])
      setIsStreaming(true)

      const path = agentId
        ? `/api/projects/${projectId}/agents/${agentId}/builder/chat`
        : `/api/projects/${projectId}/agents/builder/chat`

      try {
        const res = await fetch(`${BASE_URL}${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userText, yaml_content: yamlContent }),
        })

        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let explanation = ""
        let updatedYaml = ""
        let diff = ""
        let buffer = ""
        let hasError = false

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() ?? ""

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            try {
              const event = JSON.parse(line.slice(6))
              if (event.type === "delta" && event.text) {
                explanation += event.text
                setMessages((prev) =>
                  prev.map((m, i) =>
                    i === assistantIdx ? { ...m, content: explanation } : m,
                  ),
                )
              } else if (event.type === "explanation") {
                explanation = event.text
              } else if (event.type === "yaml_diff") {
                diff = event.diff
              } else if (event.type === "updated_yaml") {
                updatedYaml = event.yaml
              } else if (event.type === "error") {
                hasError = true
                setMessages((prev) =>
                  prev.map((m, i) =>
                    i === assistantIdx
                      ? { ...m, content: `Error: ${event.message}`, isStreaming: false }
                      : m,
                  ),
                )
              }
            } catch {
              // ignore malformed lines
            }
          }
        }

        if (!hasError) {
          if (updatedYaml) applyDiff(diff, updatedYaml)
          setMessages((prev) =>
            prev.map((m, i) =>
              i === assistantIdx
                ? { ...m, content: explanation || "Done!", isStreaming: false, hasDiff: !!diff }
                : m,
            ),
          )
        }
      } catch (err) {
        setMessages((prev) =>
          prev.map((m, i) =>
            i === assistantIdx
              ? {
                  ...m,
                  content: `Something went wrong: ${err instanceof Error ? err.message : String(err)}`,
                  isStreaming: false,
                }
              : m,
          ),
        )
      } finally {
        setIsStreaming(false)
      }
    },
    [agentId, applyDiff, isStreaming, messages.length, projectId, yamlContent],
  )

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-4 p-4">
          {messages.length === 0 ? (
            <EmptyState onSend={sendMessage} />
          ) : (
            messages.map((msg, i) => (
              <ChatMessage
                key={i}
                message={msg}
                onViewYaml={() => setActiveTab("yaml")}
              />
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <Separator />

      {/* Input */}
      <div className="flex gap-2 items-end p-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe a change… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={isStreaming}
          className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        <Button
          size="icon"
          onClick={() => sendMessage(input)}
          disabled={isStreaming || !input.trim()}
          className="self-end"
        >
          {isStreaming ? <Loader2 className="animate-spin" /> : <Send />}
        </Button>
      </div>
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState({ onSend }: { onSend: (p: string) => void }) {
  return (
    <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-6 text-center py-8">
      <div className="flex flex-col items-center gap-2">
        <div className="rounded-full bg-primary/10 p-3">
          <Wand2 className="size-6 text-primary" />
        </div>
        <h2 className="text-base font-semibold">Start building your agent</h2>
        <p className="text-sm text-muted-foreground max-w-xs">
          Describe what your agent should do in plain English. I'll generate the YAML for you.
        </p>
      </div>
      <div className="flex flex-col gap-2 w-full max-w-sm">
        {STARTER_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSend(prompt)}
            className="rounded-lg border border-border bg-card px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function ChatMessage({
  message,
  onViewYaml,
}: {
  message: Message
  onViewYaml: () => void
}) {
  const isUser = message.role === "user"

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {isUser ? "U" : "AI"}
      </div>
      <div className={`flex flex-col gap-1 max-w-[85%] ${isUser ? "items-end" : ""}`}>
        <div
          className={`rounded-lg px-3 py-2 text-sm ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-foreground"
          }`}
        >
          {message.isStreaming && !message.content ? (
            <TypingIndicator />
          ) : (
            message.content
          )}
        </div>
        {message.hasDiff && !message.isStreaming && (
          <button
            onClick={onViewYaml}
            className="text-xs text-primary hover:underline self-start"
          >
            View YAML changes →
          </button>
        )}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <span className="flex gap-1 items-center h-4">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="size-1.5 rounded-full bg-current opacity-60 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}
