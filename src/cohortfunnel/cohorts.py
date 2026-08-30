"""Cohort retention.

Three definitional choices are baked in here, and each one changes the numbers:

1. **A cohort is the period of a user's first ``signup`` event**, not the period of their
   first activity of any kind. Anchoring on signup keeps the denominator stable when the
   activity definition changes.
2. **Retention is unbounded-return, not consecutive.** A user counts as retained in
   period *k* if they fired the activity event during period *k*, whether or not they
   were active in *k-1*. Consecutive-only retention is a different (and much harsher)
   metric; mixing the two up is the most common cohort-chart error.
3. **Unobserved cells are NULL, not zero.** A cohort that signed up two weeks before the
   data ends has no week-5 number yet. Filling those with 0 drags the tail of every
   curve towards zero and makes recent cohorts look like a churn crisis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import duckdb
import pandas as pd

from .events import LESSON_START, SIGNUP
from .warehouse import filter_clause

#: ``date_trunc`` and ``date_diff`` take the part as a literal, so it cannot be bound as
#: a parameter -- it is validated against this allowlist and then interpolated.
PERIODS = ("week", "month")

RETENTION_SQL = """
WITH base AS (
    SELECT * FROM events WHERE {clause}
),
cohort AS (
    SELECT user_id, date_trunc('{period}', min(event_ts)) AS cohort_period
    FROM base
    WHERE event_name = ?
    GROUP BY user_id
),
sizes AS (
    SELECT cohort_period, count(*) AS cohort_size
    FROM cohort
    GROUP BY cohort_period
),
activity AS (
    SELECT DISTINCT user_id, date_trunc('{period}', event_ts) AS active_period
    FROM base
    WHERE event_name = ?
),
counted AS (
    SELECT
        c.cohort_period,
        date_diff('{period}', c.cohort_period, a.active_period) AS period_index,
        count(DISTINCT a.user_id) AS active_users
    FROM cohort c
    JOIN activity a ON a.user_id = c.user_id
    GROUP BY 1, 2
),
horizon AS (
    SELECT date_trunc('{period}', max(event_ts)) AS last_period FROM base
),
spine AS (
    SELECT s.cohort_period, s.cohort_size, i.period_index
    FROM sizes s
    CROSS JOIN (SELECT unnest(range(0, ? + 1)) AS period_index) i
)
SELECT
    spine.cohort_period,
    spine.cohort_size,
    spine.period_index,
    spine.period_index <= date_diff('{period}', spine.cohort_period, horizon.last_period)
        AS observed,
    CASE WHEN spine.period_index
              <= date_diff('{period}', spine.cohort_period, horizon.last_period)
         THEN coalesce(counted.active_users, 0) END AS active_users,
    CASE WHEN spine.period_index
              <= date_diff('{period}', spine.cohort_period, horizon.last_period)
         THEN coalesce(counted.active_users, 0) / spine.cohort_size END AS retention
FROM spine
CROSS JOIN horizon
LEFT JOIN counted
       ON counted.cohort_period = spine.cohort_period
      AND counted.period_index = spine.period_index
ORDER BY spine.cohort_period, spine.period_index
"""


def retention(
    con: duckdb.DuckDBPyConnection,
    *,
    period: str = "week",
    signup_event: str = SIGNUP,
    activity_event: str = LESSON_START,
    max_periods: int = 8,
    filters: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Long-form retention: one row per (cohort, period_index).

    Unobserved cells come back with ``observed = False`` and NULL counts.
    """
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}, got {period!r}")
    if max_periods < 0:
        raise ValueError("max_periods must be >= 0")

    clause, params = filter_clause(filters)
    sql = RETENTION_SQL.format(clause=clause, period=period)
    return con.execute(sql, [*params, signup_event, activity_event, max_periods]).df()


def as_matrix(long: pd.DataFrame, value: str = "retention") -> pd.DataFrame:
    """Pivot long-form retention into the triangle you actually put on a slide."""
    return long.pivot(index="cohort_period", columns="period_index", values=value)


def blended_curve(long: pd.DataFrame) -> pd.DataFrame:
    """Weighted retention per period across cohorts, using observed cells only.

    Weighting by cohort size (rather than averaging the per-cohort rates) stops a tiny
    early cohort from carrying the same weight as a campaign-sized one.
    """
    observed = long[long["observed"]]
    grouped = observed.groupby("period_index", as_index=False).agg(
        cohorts=("cohort_period", "nunique"),
        users=("cohort_size", "sum"),
        active_users=("active_users", "sum"),
    )
    grouped["retention"] = grouped["active_users"] / grouped["users"]
    return grouped
