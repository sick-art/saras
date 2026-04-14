"""
DuckDB Analytics Queries — trace observability.

All functions query the DuckDB `run_stats` and `span_stats` tables which are
populated by collector.sync_completed_run().

Public functions:
    cost_over_time(agent_id, days)        → list of {date, cost_usd}
    latency_percentiles(agent_id, days)   → {p50, p95, mean} in ms
    model_usage_breakdown(agent_id, days) → list of {model, count, total_tokens, total_cost}
    error_rates(agent_id, days)           → {total, errors, error_rate_pct}
    span_type_breakdown(agent_id, days)   → list of {span_type, count, avg_duration_ms}
"""

from __future__ import annotations

from typing import Any

import structlog

from saras.db.duckdb import get_duckdb

log = structlog.get_logger()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _agent_filter(agent_id: str | None) -> tuple[str, list]:
    """Build WHERE clause fragment and params for optional agent_id filter."""
    if agent_id:
        return "AND agent_id = ?", [agent_id]
    return "", []


def _rows_to_dicts(result) -> list[dict[str, Any]]:
    columns = [col[0] for col in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


# ── Analytics functions ────────────────────────────────────────────────────────

def cost_over_time(agent_id: str | None, days: int = 30) -> list[dict[str, Any]]:
    """
    Daily aggregated cost for the last N days.
    Returns: [{date: "YYYY-MM-DD", cost_usd: float, run_count: int}]
    """
    try:
        cond, params = _agent_filter(agent_id)
        conn = get_duckdb()
        result = conn.execute(
            f"""
            SELECT
                CAST(started_at AS DATE) AS date,
                SUM(total_cost_usd)      AS cost_usd,
                COUNT(*)                 AS run_count
            FROM run_stats
            WHERE started_at >= NOW() - INTERVAL '{days} days'
              AND status = 'completed'
              {cond}
            GROUP BY 1
            ORDER BY 1
            """,
            params,
        )
        return _rows_to_dicts(result)
    except Exception as exc:
        log.error("query.cost_over_time", error=str(exc))
        return []


def latency_percentiles(agent_id: str | None, days: int = 30) -> dict[str, Any]:
    """
    Run duration percentiles (ms) for completed runs.
    Returns: {p50: int, p95: int, mean: int, total_runs: int}
    """
    try:
        cond, params = _agent_filter(agent_id)
        conn = get_duckdb()

        # DuckDB: epoch_ms(ended_at) - epoch_ms(started_at) gives millis
        result = conn.execute(
            f"""
            SELECT
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY dur) AS p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY dur) AS p95,
                AVG(dur)                                           AS mean,
                COUNT(*)                                           AS total_runs
            FROM (
                SELECT
                    epoch_ms(ended_at) - epoch_ms(started_at) AS dur
                FROM run_stats
                WHERE started_at >= NOW() - INTERVAL '{days} days'
                  AND status = 'completed'
                  AND ended_at IS NOT NULL
                  {cond}
            ) t
            """,
            params,
        )
        row = result.fetchone()
        if row is None or row[3] == 0:
            return {"p50": 0, "p95": 0, "mean": 0, "total_runs": 0}
        return {
            "p50": int(row[0] or 0),
            "p95": int(row[1] or 0),
            "mean": int(row[2] or 0),
            "total_runs": int(row[3] or 0),
        }
    except Exception as exc:
        log.error("query.latency_percentiles", error=str(exc))
        return {"p50": 0, "p95": 0, "mean": 0, "total_runs": 0}


def model_usage_breakdown(agent_id: str | None, days: int = 30) -> list[dict[str, Any]]:
    """
    Token + cost breakdown per model for the last N days.
    Returns: [{model: str, run_count: int, total_tokens: int, total_cost_usd: float}]
    """
    try:
        cond, params = _agent_filter(agent_id)
        conn = get_duckdb()
        result = conn.execute(
            f"""
            SELECT
                COALESCE(model_primary, 'unknown') AS model,
                COUNT(*)                           AS run_count,
                SUM(total_tokens)                  AS total_tokens,
                SUM(total_cost_usd)                AS total_cost_usd
            FROM run_stats
            WHERE started_at >= NOW() - INTERVAL '{days} days'
              AND status = 'completed'
              {cond}
            GROUP BY 1
            ORDER BY total_cost_usd DESC
            """,
            params,
        )
        return _rows_to_dicts(result)
    except Exception as exc:
        log.error("query.model_usage_breakdown", error=str(exc))
        return []


def error_rates(agent_id: str | None, days: int = 30) -> dict[str, Any]:
    """
    Error rate for runs in the last N days.
    Returns: {total: int, errors: int, error_rate_pct: float}
    """
    try:
        cond, params = _agent_filter(agent_id)
        conn = get_duckdb()
        result = conn.execute(
            f"""
            SELECT
                COUNT(*)                                          AS total,
                COUNT(*) FILTER (WHERE status = 'failed')         AS errors
            FROM run_stats
            WHERE started_at >= NOW() - INTERVAL '{days} days'
              {cond}
            """,
            params,
        )
        row = result.fetchone()
        if row is None or row[0] == 0:
            return {"total": 0, "errors": 0, "error_rate_pct": 0.0}
        total, errors = int(row[0]), int(row[1])
        return {
            "total": total,
            "errors": errors,
            "error_rate_pct": round(errors / total * 100, 2),
        }
    except Exception as exc:
        log.error("query.error_rates", error=str(exc))
        return {"total": 0, "errors": 0, "error_rate_pct": 0.0}


def span_type_breakdown(agent_id: str | None, days: int = 30) -> list[dict[str, Any]]:
    """
    Per span-type call counts and average latency over the last N days.
    Returns: [{span_type: str, count: int, avg_duration_ms: int}]
    """
    try:
        conn = get_duckdb()
        # Join span_stats to run_stats to filter by agent_id
        agent_join = ""
        agent_where = ""
        params: list = [days]
        if agent_id:
            agent_join = "JOIN run_stats rs ON ss.run_id = rs.run_id"
            agent_where = "AND rs.agent_id = ?"
            params.append(agent_id)

        result = conn.execute(
            f"""
            SELECT
                ss.span_type,
                COUNT(*)               AS count,
                AVG(ss.duration_ms)    AS avg_duration_ms
            FROM span_stats ss
            {agent_join}
            WHERE ss.started_at >= NOW() - INTERVAL ? days
              {agent_where}
            GROUP BY 1
            ORDER BY count DESC
            """,
            params,
        )
        rows = _rows_to_dicts(result)
        for row in rows:
            row["avg_duration_ms"] = int(row["avg_duration_ms"] or 0)
        return rows
    except Exception as exc:
        log.error("query.span_type_breakdown", error=str(exc))
        return []


def analytics_summary(agent_id: str | None, days: int = 30) -> dict[str, Any]:
    """
    Aggregate all analytics into a single response object for the UI.
    """
    return {
        "cost_over_time": cost_over_time(agent_id, days),
        "latency": latency_percentiles(agent_id, days),
        "models": model_usage_breakdown(agent_id, days),
        "errors": error_rates(agent_id, days),
        "span_types": span_type_breakdown(agent_id, days),
    }
