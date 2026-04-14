"""Unit tests for saras.tracing.query — DuckDB analytics queries."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import duckdb
import pytest

from saras.tracing.query import (
    analytics_summary,
    cost_over_time,
    error_rates,
    latency_percentiles,
    model_usage_breakdown,
    span_type_breakdown,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mem_db():
    """
    In-memory DuckDB connection with run_stats and span_stats tables.
    Patched into saras.tracing.query via get_duckdb mock.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE run_stats (
            run_id          VARCHAR PRIMARY KEY,
            agent_id        VARCHAR NOT NULL,
            agent_version   VARCHAR NOT NULL,
            session_id      VARCHAR,
            started_at      TIMESTAMPTZ NOT NULL,
            ended_at        TIMESTAMPTZ,
            status          VARCHAR NOT NULL,
            total_tokens    INTEGER DEFAULT 0,
            total_cost_usd  DOUBLE DEFAULT 0.0,
            model_primary   VARCHAR,
            metadata        JSON
        )
    """)
    conn.execute("""
        CREATE TABLE span_stats (
            span_id         VARCHAR PRIMARY KEY,
            run_id          VARCHAR NOT NULL,
            span_type       VARCHAR NOT NULL,
            name            VARCHAR NOT NULL,
            started_at      TIMESTAMPTZ NOT NULL,
            duration_ms     INTEGER,
            model           VARCHAR,
            provider        VARCHAR,
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            cost_usd        DOUBLE DEFAULT 0.0,
            tool_name       VARCHAR,
            success         BOOLEAN DEFAULT TRUE
        )
    """)
    yield conn
    conn.close()


def seed_runs(conn, runs: list[dict]) -> None:
    for r in runs:
        conn.execute(
            """
            INSERT INTO run_stats (
                run_id, agent_id, agent_version, started_at, ended_at,
                status, total_tokens, total_cost_usd, model_primary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                r["run_id"],
                r.get("agent_id", "agent-1"),
                r.get("agent_version", "1.0.0"),
                r.get("started_at", datetime.now(timezone.utc)),
                r.get("ended_at", datetime.now(timezone.utc)),
                r.get("status", "completed"),
                r.get("total_tokens", 200),
                r.get("total_cost_usd", 0.001),
                r.get("model_primary", "gpt-4o-mini"),
            ],
        )


def seed_spans(conn, spans: list[dict]) -> None:
    for s in spans:
        conn.execute(
            """
            INSERT INTO span_stats (
                span_id, run_id, span_type, name, started_at, duration_ms,
                model, input_tokens, output_tokens, cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                s["span_id"],
                s["run_id"],
                s.get("span_type", "llm_call"),
                s.get("name", "llm_call"),
                s.get("started_at", datetime.now(timezone.utc)),
                s.get("duration_ms", 300),
                s.get("model", "gpt-4o-mini"),
                s.get("input_tokens", 100),
                s.get("output_tokens", 50),
                s.get("cost_usd", 0.0005),
            ],
        )


# ── cost_over_time ────────────────────────────────────────────────────────────

def test_cost_over_time_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = cost_over_time(agent_id=None)
    assert result == []


def test_cost_over_time_sums_daily(mem_db):
    seed_runs(mem_db, [
        {"run_id": "r1", "total_cost_usd": 0.01},
        {"run_id": "r2", "total_cost_usd": 0.02},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = cost_over_time(agent_id=None)
    assert len(result) == 1
    assert result[0]["cost_usd"] == pytest.approx(0.03, abs=1e-6)
    assert result[0]["run_count"] == 2


def test_cost_over_time_filters_by_agent(mem_db):
    seed_runs(mem_db, [
        {"run_id": "r1", "agent_id": "agent-A", "total_cost_usd": 0.05},
        {"run_id": "r2", "agent_id": "agent-B", "total_cost_usd": 0.10},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = cost_over_time(agent_id="agent-A")
    assert len(result) == 1
    assert result[0]["cost_usd"] == pytest.approx(0.05, abs=1e-6)


# ── latency_percentiles ───────────────────────────────────────────────────────

def test_latency_percentiles_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = latency_percentiles(agent_id=None)
    assert result == {"p50": 0, "p95": 0, "mean": 0, "total_runs": 0}


def test_latency_p50_lte_p95(mem_db):
    seed_runs(mem_db, [
        {"run_id": f"r{i}", "total_cost_usd": 0.001} for i in range(10)
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = latency_percentiles(agent_id=None)
    assert result["p50"] <= result["p95"]
    assert result["total_runs"] == 10


# ── model_usage_breakdown ─────────────────────────────────────────────────────

def test_model_usage_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = model_usage_breakdown(agent_id=None)
    assert result == []


def test_model_usage_groups_by_model(mem_db):
    seed_runs(mem_db, [
        {"run_id": "r1", "model_primary": "gpt-4o-mini", "total_tokens": 100, "total_cost_usd": 0.001},
        {"run_id": "r2", "model_primary": "gpt-4o-mini", "total_tokens": 200, "total_cost_usd": 0.002},
        {"run_id": "r3", "model_primary": "claude-haiku", "total_tokens": 150, "total_cost_usd": 0.003},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = model_usage_breakdown(agent_id=None)
    models = {r["model"] for r in result}
    assert "gpt-4o-mini" in models
    assert "claude-haiku" in models
    gpt_row = next(r for r in result if r["model"] == "gpt-4o-mini")
    assert gpt_row["run_count"] == 2
    assert gpt_row["total_tokens"] == 300


# ── error_rates ───────────────────────────────────────────────────────────────

def test_error_rates_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = error_rates(agent_id=None)
    assert result == {"total": 0, "errors": 0, "error_rate_pct": 0.0}


def test_error_rates_zero_errors(mem_db):
    seed_runs(mem_db, [
        {"run_id": "r1", "status": "completed"},
        {"run_id": "r2", "status": "completed"},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = error_rates(agent_id=None)
    assert result["total"] == 2
    assert result["errors"] == 0
    assert result["error_rate_pct"] == 0.0


def test_error_rates_with_failures(mem_db):
    seed_runs(mem_db, [
        {"run_id": "r1", "status": "completed"},
        {"run_id": "r2", "status": "failed"},
        {"run_id": "r3", "status": "failed"},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = error_rates(agent_id=None)
    assert result["total"] == 3
    assert result["errors"] == 2
    assert result["error_rate_pct"] == pytest.approx(66.67, abs=0.01)


# ── span_type_breakdown ───────────────────────────────────────────────────────

def test_span_type_breakdown_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = span_type_breakdown(agent_id=None)
    assert result == []


def test_span_type_breakdown_groups_correctly(mem_db):
    seed_runs(mem_db, [{"run_id": "r1"}])
    seed_spans(mem_db, [
        {"span_id": "s1", "run_id": "r1", "span_type": "llm_call", "duration_ms": 200},
        {"span_id": "s2", "run_id": "r1", "span_type": "llm_call", "duration_ms": 400},
        {"span_id": "s3", "run_id": "r1", "span_type": "tool_call", "duration_ms": 100},
    ])
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = span_type_breakdown(agent_id=None)
    span_types = {r["span_type"] for r in result}
    assert "llm_call" in span_types
    assert "tool_call" in span_types
    llm_row = next(r for r in result if r["span_type"] == "llm_call")
    assert llm_row["count"] == 2
    assert llm_row["avg_duration_ms"] == 300


# ── analytics_summary ─────────────────────────────────────────────────────────

def test_analytics_summary_returns_all_keys(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = analytics_summary(agent_id=None)
    assert "cost_over_time" in result
    assert "latency" in result
    assert "models" in result
    assert "errors" in result
    assert "span_types" in result


def test_analytics_summary_graceful_on_empty_db(mem_db):
    with patch("saras.tracing.query.get_duckdb", return_value=mem_db):
        result = analytics_summary(agent_id="nonexistent-agent")
    assert result["errors"]["total"] == 0
    assert result["latency"]["p50"] == 0
