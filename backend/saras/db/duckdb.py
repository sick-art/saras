"""
DuckDB analytics engine — embedded OLAP queries over trace/run data.
Used for cost over time, latency percentiles, model usage breakdowns, etc.
"""

from pathlib import Path
import duckdb

from saras.config import get_settings

_conn: duckdb.DuckDBPyConnection | None = None


def get_duckdb() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        settings = get_settings()
        path = Path(settings.duckdb_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(path))
        _bootstrap(_conn)
    return _conn


def _bootstrap(conn: duckdb.DuckDBPyConnection) -> None:
    """Create analytics views on first connect."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_stats (
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
        CREATE TABLE IF NOT EXISTS span_stats (
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


def close() -> None:
    global _conn
    if _conn:
        _conn.close()
        _conn = None
