"""
LiteLLM adapter — unified interface to Claude, GPT, Gemini, and any BYO model.

Responsibilities:
- Async chat completion (streaming and non-streaming)
- Token counting and cost estimation
- Provider API key injection from Settings
- Retry logic via tenacity (exponential backoff, 3 attempts)
- Convert Saras ToolDefinition format to LiteLLM-compatible tool format

What it does NOT do:
- Interpret tool calls or execute tool logic (that's executor.py)
- Store anything to DB
- Know anything about agent schema or conditions
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import litellm
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from saras.config import get_settings
from saras.core.schema import ToolDefinition

log = structlog.get_logger()

# Silence litellm's chatty default logging
litellm.set_verbose = False


# ── Public types ───────────────────────────────────────────────────────────────

class LLMMessage(dict):
    """Typed alias — a dict with 'role' and 'content' keys."""


class LLMResponse:
    """Parsed response from a non-streaming LLM call."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    @property
    def content(self) -> str:
        choice = self._raw.choices[0]
        if choice.message.content:
            return choice.message.content
        return ""

    @property
    def tool_calls(self) -> list[dict]:
        """Return list of {id, name, arguments_dict} for any tool calls."""
        choice = self._raw.choices[0]
        if not choice.message.tool_calls:
            return []
        result = []
        for tc in choice.message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                args = {}
            result.append({"id": tc.id, "name": tc.function.name, "arguments": args})
        return result

    @property
    def stop_reason(self) -> str:
        return self._raw.choices[0].finish_reason or "stop"

    @property
    def usage(self) -> dict:
        u = self._raw.usage
        return {
            "input_tokens": u.prompt_tokens if u else 0,
            "output_tokens": u.completion_tokens if u else 0,
        }


# ── Key injection ──────────────────────────────────────────────────────────────

def _build_api_kwargs(model: str) -> dict:
    """Return provider-specific API key kwargs for LiteLLM."""
    settings = get_settings()
    kwargs: dict = {}

    if model.startswith("claude") or model.startswith("anthropic/"):
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
    elif model.startswith("gpt") or model.startswith("openai/"):
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
    elif model.startswith("gemini") or model.startswith("google/"):
        if settings.google_api_key:
            kwargs["api_key"] = settings.google_api_key

    return kwargs


# ── Tool format conversion ─────────────────────────────────────────────────────

def _to_litellm_tools(tool_defs: list[ToolDefinition]) -> list[dict]:
    """
    Convert Saras ToolDefinition list to LiteLLM-compatible tool format.
    LiteLLM normalises across Anthropic tool_use and OpenAI function_calling.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": td.name,
                "description": td.description,
                "parameters": td.input_schema,
            },
        }
        for td in tool_defs
    ]


# ── Core completion ────────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type((litellm.exceptions.APIConnectionError,
                                   litellm.exceptions.Timeout)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def chat_completion(
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition] | None = None,
    stream: bool = False,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> LLMResponse:
    """
    Single non-streaming LLM call. Retries on connection errors.

    Args:
        model: LiteLLM model string, e.g. "claude-sonnet-4-6", "gpt-4o".
        messages: Conversation messages in OpenAI format.
        tools: Saras ToolDefinition list; converted to LiteLLM format internally.
        stream: Must be False for this function (use stream_completion for streaming).
        temperature: Sampling temperature.
        max_tokens: Max output tokens.

    Returns:
        LLMResponse wrapping the raw LiteLLM response.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **_build_api_kwargs(model),
    }
    if tools:
        kwargs["tools"] = _to_litellm_tools(tools)

    log.debug("litellm.chat_completion", model=model, n_messages=len(messages),
              n_tools=len(tools) if tools else 0)

    raw = await litellm.acompletion(**kwargs)
    return LLMResponse(raw)


async def stream_completion(
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """
    Streaming LLM call. Yields text delta chunks as plain strings.
    Tool call chunks are yielded as JSON-encoded strings prefixed with '__tool__:'.

    Usage:
        async for chunk in stream_completion(model, messages):
            # plain text delta
            print(chunk)
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        **_build_api_kwargs(model),
    }
    if tools:
        kwargs["tools"] = _to_litellm_tools(tools)

    log.debug("litellm.stream_completion", model=model, n_messages=len(messages))

    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue
        if delta.content:
            yield delta.content
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if tc.function and tc.function.name:
                    yield f"__tool__:{json.dumps({'name': tc.function.name, 'arguments': tc.function.arguments or ''})}"


# ── Token counting ─────────────────────────────────────────────────────────────

def count_tokens(model: str, messages: list[dict]) -> int:
    """
    Estimate token count for a message list using LiteLLM's token counter.
    Returns 0 on any error (non-critical; used for observability only).
    """
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:
        return 0


# ── Cost estimation ────────────────────────────────────────────────────────────

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimate the USD cost of a completion.
    Returns 0.0 if the model is unknown to LiteLLM's cost DB.
    """
    try:
        return litellm.completion_cost(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
    except Exception:
        return 0.0
