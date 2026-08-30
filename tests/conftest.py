"""Hand-built warehouses.

Every expected number in these tests was worked out on paper from the rows below, not
copied from a first run. A fixture that only asserts what the code already does cannot
catch the code being wrong.
"""

from __future__ import annotations

import datetime as dt

import pytest

from cohortfunnel import warehouse

W0 = dt.date(2026, 1, 5)  # Monday
W1 = dt.date(2026, 1, 12)
W2 = dt.date(2026, 1, 19)


def ts(day: dt.date, offset_days: int = 0, hour: int = 10) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour)) + dt.timedelta(days=offset_days)


def row(user: str, when: dt.datetime, event: str, channel: str = "organic", platform: str = "web"):
    return (user, when, event, channel, platform)


@pytest.fixture
def retention_con():
    """Cohort W0 has 3 users, cohort W1 has 1. Last event is in W2."""
    rows = [
        row("u1", ts(W0), "signup"),
        row("u1", ts(W0, 1), "lesson_start"),
        row("u1", ts(W1, 2), "lesson_start"),
        row("u2", ts(W0, 1), "signup"),
        row("u2", ts(W1, 3), "lesson_start"),
        row("u3", ts(W0, 2), "signup"),
        row("u4", ts(W1), "signup"),
        row("u4", ts(W1, 1), "lesson_start"),
        row("u4", ts(W2, 1), "lesson_start"),
    ]
    con = warehouse.in_memory(rows)
    yield con
    con.close()


@pytest.fixture
def funnel_con():
    """Four users, each demonstrating exactly one funnel subtlety.

    * ``clean``   -- all three steps, in order, inside a day.
    * ``late``    -- starts the lesson 10 days after signup (outside a 7-day window).
    * ``jumbled`` -- completes a lesson without ever starting one (order violation).
    * ``paid``    -- signs up only.
    """
    rows = [
        row("clean", ts(W0, 0, 9), "signup"),
        row("clean", ts(W0, 0, 11), "lesson_start"),
        row("clean", ts(W0, 0, 12), "lesson_complete"),
        row("late", ts(W0, 0, 9), "signup"),
        row("late", ts(W0, 10, 9), "lesson_start"),
        row("late", ts(W0, 10, 12), "lesson_complete"),
        row("jumbled", ts(W0, 0, 9), "signup"),
        row("jumbled", ts(W0, 1, 9), "lesson_complete"),
        row("paid", ts(W0, 0, 9), "signup"),
    ]
    con = warehouse.in_memory(rows)
    yield con
    con.close()


STEPS = ["signup", "lesson_start", "lesson_complete"]
