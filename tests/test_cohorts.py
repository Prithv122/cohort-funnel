from __future__ import annotations

import math

import pandas as pd
import pytest

from cohortfunnel import cohorts


def cell(long, cohort_index: int, period_index: int, column: str = "retention"):
    cohort = sorted(long["cohort_period"].unique())[cohort_index]
    match = long[(long["cohort_period"] == cohort) & (long["period_index"] == period_index)]
    return match[column].iloc[0]


def test_retention_values_are_share_of_cohort(retention_con):
    long = cohorts.retention(retention_con, max_periods=3)
    # Cohort W0: 3 signups, u1 active in week 0, u1+u2 in week 1, nobody in week 2.
    assert cell(long, 0, 0) == pytest.approx(1 / 3)
    assert cell(long, 0, 1) == pytest.approx(2 / 3)
    assert cell(long, 0, 2) == pytest.approx(0.0)
    # Cohort W1: one signup, active in both of its observed weeks.
    assert cell(long, 1, 0) == pytest.approx(1.0)
    assert cell(long, 1, 1) == pytest.approx(1.0)


def test_unobserved_periods_are_null_not_zero(retention_con):
    """The W1 cohort has no week-2 number yet. Zero would be a lie about churn."""
    long = cohorts.retention(retention_con, max_periods=3)
    assert cell(long, 1, 1, "observed")
    assert not cell(long, 1, 2, "observed")
    assert math.isnan(cell(long, 1, 2))
    assert pd.isna(cell(long, 1, 2, "active_users"))
    # The older cohort has seen week 2 -- a real zero, kept as zero.
    assert cell(long, 0, 2, "observed")
    assert cell(long, 0, 2) == 0.0


def test_cohort_size_is_signups_not_actives(retention_con):
    long = cohorts.retention(retention_con, max_periods=3)
    assert cell(long, 0, 0, "cohort_size") == 3


def test_blended_curve_is_size_weighted(retention_con):
    long = cohorts.retention(retention_con, max_periods=3)
    curve = cohorts.blended_curve(long)
    period0 = curve[curve["period_index"] == 0].iloc[0]
    # 2 of 4 users active in their own signup week -- not the mean of 0.333 and 1.0.
    assert period0["retention"] == pytest.approx(0.5)
    assert period0["users"] == 4


def test_matrix_shape(retention_con):
    long = cohorts.retention(retention_con, max_periods=3)
    matrix = cohorts.as_matrix(long)
    assert matrix.shape == (2, 4)
    assert list(matrix.columns) == [0, 1, 2, 3]


def test_filters_apply_to_both_cohort_and_activity(retention_con):
    long = cohorts.retention(retention_con, max_periods=3, filters={"platform": ["ios"]})
    assert long.empty


def test_period_is_allowlisted(retention_con):
    with pytest.raises(ValueError, match="period must be one of"):
        cohorts.retention(retention_con, period="week'); DROP TABLE events; --")
