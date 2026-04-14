"""
Trace Collector — DuckDB sync layer for completed runs and spans.

Responsibilities:
  - After a Run completes in Postgres, sync it (and its Spans) to DuckDB for
    fast OLAP analytics queries (cost over time, latency percentiles, etc.).
  - extract_span_analytics() pulls model/provider/token fields out of the
    span payload so DuckDB rows are queryable without JSON parsing.

Usage:
    from saras.tracing.collector import sync_completed_run
    await sync_completed_run(run_id, db_session)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saras.db.duckdb import get_duckdb
from saras.db.models import Run, Span

log = structlog.get_logger()


# ── Analytics extraction helpers ──────────────────────────────────────────────

def _ts(dt: datetime | None) -> str | None:
    """Convert a datetime to ISO-8601 string with timezone for DuckDB."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _extract_run_model(spans: list[Span]) -> str | None:
    """Pull the primary model name from the first llm_call_end span."""
    for span in spans:
        if span.type == "llm_call_end" and span.payload:
            model = span.payload.get("model")
            if model:
                return str(model)
    # Fallback: check router_decision span
    for span in spans:
        if span.type == "router_decision" and span.payload:
            model = span.payload.get("model")
            if model:
                return str(model)
    return None


def _extract_span_analytics(span: Span) -> dict[str, Any]:
    """
    Flatten span payload fields relevant to analytics into a flat dict.
    Returns the values needed to populate span_stats.
    """
    payload: dict[str, Any] = span.payload or {}
    return {
        "model": payload.get("model"),
        "provider": _provider_from_model(payload.get("model")),
        "input_tokens": payload.get("input_tokens", 0),
        "output_tokens": payload.get("output_tokens", 0),
        "cost_usd": payload.get("cost_usd", 0.0),
        "tool_name": payload.get("tool"),
        "success": not payload.get("error"),
    }


def _provider_from_model(model: str | None) -> str | None:
    """Infer provider name from model string."""
    if not model:
        return None
    m = model.lower()
    if m.startswith("claude") or "anthropic" in m:
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or "openai" in m:
        return "openai"
    if m.startswith("gemini") or "google" in m:
        return "google"
    return "other"


# ── Public API ─────────────────────────────────────────────────────────────────

async def sync_completed_run(run_id: str, db: AsyncSession) -> None:
    """
    Sync a completed Run and all its Spans from Postgres → DuckDB.

    Safe to call multiple times (upsert semantics).
    Logs and swallows DuckDB errors so they never break the main execution path.
    """
    try:
        # Load Run
        run: Run | None = await db.get(Run, run_id)
        if run is None:
            log.warning("collector.run_not_found", run_id=run_id)
            return

        # Load Spans
        result = await db.execute(select(Span).where(Span.run_id == run_id))
        spans: list[Span] = list(result.scalars().all())

        _upsert_run(run, spans)
        for span in spans:
            _upsert_span(span)

        log.info("collector.synced", run_id=run_id, spans=len(spans))

    except Exception as exc:
        log.error("collector.sync_error", run_id=run_id, error=str(exc))


def _upsert_run(run: Run, spans: list[Span]) -> None:
    conn = get_duckdb()
    model_primary = _extract_run_model(spans)

    conn.execute(
        """
        INSERT OR REPLACE INTO run_stats (
            run_id, agent_id, agent_version, session_id,
            started_at, ended_at, status, total_tokens,
            total_cost_usd, model_primary, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run.id,
            run.agent_id or "",
            run.agent_version or "",
            run.session_id,
            _ts(run.started_at),
            _ts(run.ended_at),
            run.status,
            run.total_tokens or 0,
            run.total_cost_usd or 0.0,
            model_primary,
            json.dumps(run.metadata_) if run.metadata_ else None,
        ],
    )


def _upsert_span(span: Span) -> None:
    conn = get_duckdb()
    analytics = _extract_span_analytics(span)

    conn.execute(
        """
        INSERT OR REPLACE INTO span_stats (
            span_id, run_id, span_type, name,
            started_at, duration_ms, model, provider,
            input_tokens, output_tokens, cost_usd,
            tool_name, success
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            span.id,
            span.run_id,
            span.type,
            span.name,
            _ts(span.started_at),
            span.duration_ms,
            analytics["model"],
            analytics["provider"],
            analytics["input_tokens"],
            analytics["output_tokens"],
            analytics["cost_usd"],
            analytics["tool_name"],
            analytics["success"],
        ],
    )
