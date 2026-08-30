"""Step-ordered funnels with a conversion window.

The naive funnel -- ``count(DISTINCT user_id)`` per event, one query per step -- is what
most dashboards ship, and it is wrong in two specific ways:

* it ignores **order**, so a user who subscribed via a referral code and never passed a
  quiz still lands in the final step;
* it ignores **time**, so someone who signed up in January and converted in March counts
  as the same conversion as someone who converted in an hour.

The funnel here fixes both. Each step must occur strictly after the previous step and
within a conversion window. ``window_from="entry"`` measures the window from the first
step (the usual product definition: "converted within 7 days of signup");
``window_from="previous"`` measures it from the preceding step, which is the right choice
for a checkout flow where each step should follow quickly on the last.

Step names arrive from the caller -- the CLI, the dashboard sidebar -- and are always
bound as parameters, never formatted into the SQL text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import duckdb
import pandas as pd

from .warehouse import filter_clause

WINDOW_ANCHORS = ("entry", "previous")

DEFAULT_WINDOW_HOURS = 24 * 7


def _validate(steps: Sequence[str], window_hours: float, window_from: str) -> None:
    if len(steps) < 2:
        raise ValueError("A funnel needs at least two steps")
    if len(set(steps)) != len(steps):
        raise ValueError("Funnel steps must be distinct")
    if not all(isinstance(step, str) and step for step in steps):
        raise ValueError("Funnel steps must be non-empty strings")
    if window_hours <= 0:
        raise ValueError("window_hours must be positive")
    if window_from not in WINDOW_ANCHORS:
        raise ValueError(f"window_from must be one of {WINDOW_ANCHORS}, got {window_from!r}")


def build_sql(steps: Sequence[str], clause: str, window_from: str) -> str:
    """Return the funnel SQL. Every value is a placeholder; only the shape varies."""
    ctes = [
        f"base AS (SELECT * FROM events WHERE {clause})",
        "s0 AS (SELECT user_id, min(event_ts) AS t0 FROM base WHERE event_name = ? GROUP BY 1)",
    ]
    for i in range(1, len(steps)):
        anchor = "p.t0" if window_from == "entry" else f"p.t{i - 1}"
        ctes.append(
            f"s{i} AS ("
            f" SELECT p.user_id, p.t0, min(e.event_ts) AS t{i}"
            f" FROM base e JOIN s{i - 1} p ON e.user_id = p.user_id"
            f" WHERE e.event_name = ?"
            f"   AND e.event_ts > p.t{i - 1}"
            f"   AND e.event_ts <= {anchor} + to_seconds(?)"
            f" GROUP BY 1, 2)"
        )

    selects = [
        "SELECT 0 AS step_index, ? AS step_name, count(*) AS users, 0.0 AS median_hours FROM s0"
    ]
    for i in range(1, len(steps)):
        selects.append(
            f"SELECT {i}, ?, count(*), median(date_diff('second', t0, t{i})) / 3600.0 FROM s{i}"
        )

    return (
        "WITH " + ",\n".join(ctes) + "\n" + "\nUNION ALL\n".join(selects) + "\nORDER BY step_index"
    )


def _decorate(frame: pd.DataFrame) -> pd.DataFrame:
    entered = frame["users"].iloc[0]
    previous = frame["users"].shift(1)
    frame["step_conversion"] = (frame["users"] / previous).fillna(1.0)
    frame["overall_conversion"] = frame["users"] / entered if entered else 0.0
    frame["dropped"] = (previous - frame["users"]).fillna(0).astype("int64")
    return frame


def funnel(
    con: duckdb.DuckDBPyConnection,
    steps: Sequence[str],
    *,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    window_from: str = "entry",
    filters: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Step-ordered, time-windowed funnel. One row per step."""
    _validate(steps, window_hours, window_from)
    clause, params = filter_clause(filters)
    window_seconds = int(window_hours * 3600)

    bound: list[object] = [*params, steps[0]]
    for step in steps[1:]:
        bound += [step, window_seconds]
    bound += list(steps)

    frame = con.execute(build_sql(steps, clause, window_from), bound).df()
    return _decorate(frame)


def naive_funnel(
    con: duckdb.DuckDBPyConnection,
    steps: Sequence[str],
    *,
    filters: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """ "Did this user ever fire this event" -- the wrong answer, kept for comparison."""
    _validate(steps, 1, "entry")
    clause, params = filter_clause(filters)
    selects = "\nUNION ALL\n".join(
        f"SELECT {i} AS step_index, ? AS step_name, count(DISTINCT user_id) AS users"
        f" FROM base WHERE event_name = ?"
        for i in range(len(steps))
    )
    sql = f"WITH base AS (SELECT * FROM events WHERE {clause})\n{selects}\nORDER BY step_index"
    bound: list[object] = list(params)
    for step in steps:
        bound += [step, step]
    frame = con.execute(sql, bound).df()
    frame["median_hours"] = pd.NA
    return _decorate(frame)


def compare(
    con: duckdb.DuckDBPyConnection,
    steps: Sequence[str],
    *,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    window_from: str = "entry",
    filters: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Ordered vs naive, side by side -- the table the README quotes."""
    ordered = funnel(
        con, steps, window_hours=window_hours, window_from=window_from, filters=filters
    )
    naive = naive_funnel(con, steps, filters=filters)
    out = ordered[["step_index", "step_name", "users", "overall_conversion"]].merge(
        naive[["step_index", "users", "overall_conversion"]],
        on="step_index",
        suffixes=("_ordered", "_naive"),
    )
    out["overcount"] = out["users_naive"] - out["users_ordered"]
    return out
