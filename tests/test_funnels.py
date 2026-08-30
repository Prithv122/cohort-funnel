from __future__ import annotations

import pytest

from cohortfunnel import funnels
from conftest import STEPS


def counts(frame) -> list[int]:
    return [int(n) for n in frame["users"]]


def test_ordered_funnel_drops_out_of_order_users(funnel_con):
    """`jumbled` completed a lesson it never started; it must not reach step 2."""
    frame = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30)
    assert counts(frame) == [4, 2, 2]


def test_naive_funnel_overcounts_the_same_data(funnel_con):
    """The naive version credits `jumbled` with a completion. This is the bug."""
    frame = funnels.naive_funnel(funnel_con, STEPS)
    assert counts(frame) == [4, 2, 3]


def test_conversion_window_excludes_late_activation(funnel_con):
    inside = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30)
    outside = funnels.funnel(funnel_con, STEPS, window_hours=24 * 7)
    assert counts(inside) == [4, 2, 2]
    assert counts(outside) == [4, 1, 1]


def test_window_from_previous_is_more_permissive_here(funnel_con):
    """`late` starts on day 10 then completes 3h later: rejected from entry, kept from previous."""
    from_entry = funnels.funnel(funnel_con, STEPS, window_hours=24 * 11, window_from="entry")
    from_prev = funnels.funnel(funnel_con, STEPS, window_hours=24, window_from="previous")
    assert counts(from_entry) == [4, 2, 2]
    assert counts(from_prev) == [4, 1, 1]


def test_conversion_rates(funnel_con):
    frame = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30)
    assert list(frame["step_conversion"].round(3)) == [1.0, 0.5, 1.0]
    assert list(frame["overall_conversion"].round(3)) == [1.0, 0.5, 0.5]
    assert list(frame["dropped"]) == [0, 2, 0]


def test_median_hours_from_entry(funnel_con):
    """clean: 2h to start. late: 240h. Median of the two = 121h."""
    frame = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30)
    assert frame["median_hours"].iloc[0] == 0.0
    assert frame["median_hours"].iloc[1] == pytest.approx(121.0)


def test_compare_reports_the_overcount(funnel_con):
    frame = funnels.compare(funnel_con, STEPS, window_hours=24 * 7)
    assert list(frame["overcount"]) == [0, 1, 2]


def test_filters_bind_values_and_allowlist_columns(funnel_con):
    ok = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30, filters={"channel": ["organic"]})
    assert counts(ok)[0] == 4

    none = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30, filters={"channel": ["paid"]})
    assert counts(none)[0] == 0

    with pytest.raises(ValueError, match="Not a filterable column"):
        funnels.funnel(funnel_con, STEPS, filters={"user_id; DROP TABLE events": ["x"]})


def test_injection_in_a_filter_value_is_inert(funnel_con):
    """A hostile *value* is bound, so it matches nothing and the table survives."""
    hostile = "organic' OR '1'='1"
    frame = funnels.funnel(funnel_con, STEPS, window_hours=24 * 30, filters={"channel": [hostile]})
    assert counts(frame)[0] == 0
    assert funnel_con.execute("SELECT count(*) FROM events").fetchone()[0] == 9


@pytest.mark.parametrize(
    ("steps", "kwargs", "match"),
    [
        (["signup"], {}, "at least two"),
        (["a", "a"], {}, "distinct"),
        (["a", "b"], {"window_hours": 0}, "positive"),
        (["a", "b"], {"window_from": "sideways"}, "window_from"),
    ],
)
def test_validation(funnel_con, steps, kwargs, match):
    with pytest.raises(ValueError, match=match):
        funnels.funnel(funnel_con, steps, **kwargs)
