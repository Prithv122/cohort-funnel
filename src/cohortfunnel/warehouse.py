"""DuckDB warehouse: build it, connect to it, and filter it safely.

The event table is tiny by warehouse standards (~70k rows), but the queries are written
the way they would be against a real one: all aggregation happens in SQL, and nothing
larger than a result set is ever pulled into pandas.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import duckdb

from .events import SEED, WEEKS, generate_events

DEFAULT_DB = Path("data") / "cohorts.duckdb"

#: Columns a caller may filter on. Filters are interpolated into SQL as *column names*,
#: which cannot be bound as parameters, so the allowlist is the security boundary; the
#: values themselves are always bound.
FILTERABLE = ("channel", "platform", "event_name")

SCHEMA = """
CREATE TABLE events (
    user_id     VARCHAR   NOT NULL,
    event_ts    TIMESTAMP NOT NULL,
    event_name  VARCHAR   NOT NULL,
    channel     VARCHAR   NOT NULL,
    platform    VARCHAR   NOT NULL
);
"""


def build(database: Path = DEFAULT_DB, seed: int = SEED, weeks: int = WEEKS) -> int:
    """(Re)build the warehouse from the generator. Returns the row count."""
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()

    rows = generate_events(seed=seed, weeks=weeks)
    con = duckdb.connect(str(database))
    try:
        con.execute(SCHEMA)
        con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", rows)
        # Analytical queries all start by filtering on event_name then grouping by user.
        con.execute("CREATE INDEX idx_events_name_user ON events (event_name, user_id)")
        return con.execute("SELECT count(*) FROM events").fetchone()[0]
    finally:
        con.close()


def connect(database: Path = DEFAULT_DB, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    database = Path(database)
    if not database.exists():
        raise FileNotFoundError(
            f"No warehouse at {database}. Build it first:  uv run cohort-funnel build"
        )
    return duckdb.connect(str(database), read_only=read_only)


def in_memory(rows: Sequence[tuple]) -> duckdb.DuckDBPyConnection:
    """An events warehouse held in memory -- used by the tests and by nothing else."""
    con = duckdb.connect()
    con.execute(SCHEMA)
    if rows:
        con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", list(rows))
    return con


def filter_clause(filters: Mapping[str, Sequence[str]] | None) -> tuple[str, list[str]]:
    """Build a WHERE fragment plus its bound parameters from a column -> values mapping.

    Raises ``ValueError`` on any column outside :data:`FILTERABLE`, so a malicious or
    mistyped column name can never reach the SQL text.
    """
    if not filters:
        return "TRUE", []

    fragments: list[str] = []
    params: list[str] = []
    for column, values in filters.items():
        if column not in FILTERABLE:
            raise ValueError(f"Not a filterable column: {column!r}. Allowed: {FILTERABLE}")
        values = list(values)
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        fragments.append(f"{column} IN ({placeholders})")
        params.extend(values)

    return (" AND ".join(fragments) or "TRUE"), params


def distinct_values(con: duckdb.DuckDBPyConnection, column: str) -> list[str]:
    if column not in FILTERABLE:
        raise ValueError(f"Not a filterable column: {column!r}. Allowed: {FILTERABLE}")
    rows = con.execute(f"SELECT DISTINCT {column} FROM events ORDER BY 1").fetchall()
    return [row[0] for row in rows]
