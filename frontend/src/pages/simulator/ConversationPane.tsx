/**
 * ConversationPane — left panel of SimulatorLayout.
 *
 * Renders the conversation history and provides the message input.
 * Turn types have distinct visual styles:
 *   response  → standard chat bubble
 *   slot_fill → amber "needs info" tint
 *   interrupt → red emergency override tint
 *   handoff   → purple transfer notice tint
 *
 * Token + cost metadata appears below each agent message once turn_end fires.
 */

import { useRef, useEffect, useState, type FormEvent } from "react"
import { Send, Bot, User, AlertTriangle, ArrowRightLeft, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { SimMessage, TurnType, WsStatus } from "./SimulatorLayout"

// ── Turn type metadata ─────────────────────────────────────────────────────────

const TURN_META: Record<TurnType, {
  label: string
  bubble: string
  Icon: React.ComponentType<{ className?: string }>
}> = {
  response:  { label: "Response",  bubble: "bg-card border-border",              Icon: Bot },
  slot_fill: { label: "Needs info", bubble: "bg-amber-500/5 border-amber-500/30", Icon: Info },
  interrupt: { label: "Interrupt",  bubble: "bg-red-500/5 border-red-500/30",     Icon: AlertTriangle },
  handoff:   { label: "Handoff",    bubble: "bg-purple-500/5 border-purple-500/30", Icon: ArrowRightLeft },
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface Props {
  messages: SimMessage[]
  isThinking: boolean
  wsStatus: WsStatus
  onSend: (content: string) => void
}

// ── ConversationPane ───────────────────────────────────────────────────────────

export function ConversationPane({ messages, isThinking, wsStatus, onSend }: Props) {
  const [input, setInput] = useState("")
  const scrollRef  = useRef<HTMLDivElement>(null)
  const inputRef   = useRef<HTMLTextAreaElement>(null)

  // Scroll to bottom when messages change or thinking state changes
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, isThinking])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || wsStatus !== "connected") return
    onSend(trimmed)
    setInput("")
    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = "auto"
      inputRef.current.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as FormEvent)
    }
  }

  const disabled = wsStatus !== "connected"
  const canSend  = !disabled && input.trim().length > 0

  const placeholder =
    wsStatus === "ended"    ? "Session ended — start a new session to continue" :
    wsStatus === "connected" ? "Send a message… (Enter to send)" :
    "Connecting…"

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Messages scroll area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scroll-smooth">
        {messages.length === 0 && !isThinking && (
          <EmptyState />
        )}

        {messages.map(msg => (
          <MessageRow key={msg.id} message={msg} />
        ))}

        {isThinking && <ThinkingBubble />}
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-border p-3">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none overflow-hidden rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 min-h-[36px] max-h-[120px]"
            onInput={e => {
              const el = e.currentTarget
              el.style.height = "auto"
              el.style.height = `${Math.min(el.scrollHeight, 120)}px`
            }}
          />
          <Button type="submit" size="icon-sm" disabled={!canSend} className="shrink-0 mb-px">
            <Send />
          </Button>
        </form>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  )
}

// ── Message row ────────────────────────────────────────────────────────────────

function MessageRow({ message }: { message: SimMessage }) {
  const { role } = message

  // User message
  if (role === "user") {
    return (
      <div className="flex justify-end gap-2 items-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground leading-relaxed">
          {message.content}
        </div>
        <User className="size-5 shrink-0 text-muted-foreground mb-0.5" />
      </div>
    )
  }

  // System notice (connected, reset, etc.)
  if (role === "system") {
    return (
      <div className="flex justify-center py-0.5">
        <span className="text-[11px] text-muted-foreground bg-muted px-3 py-0.5 rounded-full">
          {message.content}
        </span>
      </div>
    )
  }

  // Error
  if (role === "error") {
    return (
      <div className="flex gap-2 items-start">
        <AlertTriangle className="size-4 mt-0.5 shrink-0 text-destructive" />
        <div className="text-sm text-destructive leading-relaxed">{message.content}</div>
      </div>
    )
  }

  // Agent message
  const turnType = (message.turn_type ?? "response") as TurnType
  const meta     = TURN_META[turnType] ?? TURN_META.response
  const { Icon, bubble, label } = meta

  return (
    <div className="flex gap-2 items-start">
      {/* Avatar */}
      <div className={`size-6 mt-0.5 shrink-0 rounded-full border flex items-center justify-center ${bubble}`}>
        <Icon className="size-3" />
      </div>

      {/* Bubble + meta */}
      <div className="flex-1 min-w-0">
        <div className={`rounded-2xl rounded-tl-sm border px-3 py-2 text-sm leading-relaxed ${bubble}`}>
          {message.content}
        </div>

        {/* Below-bubble meta row */}
        <div className="mt-1 flex items-center gap-2 pl-0.5">
          {turnType !== "response" && (
            <Badge variant="outline" className="text-[9px] h-4 px-1">{label}</Badge>
          )}
          {message.tokens && (
            <span className="text-[10px] text-muted-foreground">
              {(message.tokens.input + message.tokens.output).toLocaleString()} tok
              {message.cost_usd !== undefined && message.cost_usd > 0 && (
                <> · ${message.cost_usd.toFixed(5)}</>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Thinking indicator ─────────────────────────────────────────────────────────

function ThinkingBubble() {
  return (
    <div className="flex gap-2 items-start">
      <div className="size-6 mt-0.5 shrink-0 rounded-full border border-border bg-card flex items-center justify-center">
        <Bot className="size-3 text-muted-foreground" />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border bg-card px-3 py-2.5">
        <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:0ms]" />
        <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:150ms]" />
        <span className="size-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 text-center py-16">
      <Bot className="size-8 text-muted-foreground/30" />
      <p className="text-sm font-medium text-muted-foreground">Start a conversation</p>
      <p className="text-xs text-muted-foreground/70 max-w-xs">
        Type a message to begin simulating this agent. Watch the graph light up as spans fire.
      </p>
    </div>
  )
}
