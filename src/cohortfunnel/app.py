"""Streamlit dashboard.

Run it with:  uv run streamlit run src/cohortfunnel/app.py

Imports are absolute because Streamlit executes this file as a script, not as part of the
package -- relative imports raise ImportError under `streamlit run`.

The dashboard is deliberately thin -- every number on it comes from the same functions
the CLI and the tests call, so there is exactly one implementation of each metric.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cohortfunnel import cohorts, funnels, warehouse
from cohortfunnel.events import FUNNEL_STEPS

st.set_page_config(page_title="Cohort & Funnel Analytics", layout="wide")


@st.cache_resource
def _connection(database: str):
    path = Path(database)
    if not path.exists():
        warehouse.build(path)
    return warehouse.connect(path)


@st.cache_data(show_spinner=False)
def _retention(database: str, period: str, activity: str, periods: int, filters: str):
    con = _connection(database)
    return cohorts.retention(
        con,
        period=period,
        activity_event=activity,
        max_periods=periods,
        filters=_decode(filters),
    )


@st.cache_data(show_spinner=False)
def _funnel(database: str, window: float, anchor: str, filters: str, naive: bool):
    con = _connection(database)
    if naive:
        return funnels.naive_funnel(con, list(FUNNEL_STEPS), filters=_decode(filters))
    return funnels.funnel(
        con,
        list(FUNNEL_STEPS),
        window_hours=window,
        window_from=anchor,
        filters=_decode(filters),
    )


def _encode(filters: dict[str, list[str]]) -> str:
    """Streamlit caches on hashable args, so filters travel as a stable string."""
    return "|".join(f"{k}={','.join(sorted(v))}" for k, v in sorted(filters.items()) if v)


def _decode(encoded: str) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for part in filter(None, encoded.split("|")):
        column, _, values = part.partition("=")
        filters[column] = values.split(",")
    return filters


def main() -> None:
    st.title("Cohort & funnel analytics")
    st.caption(
        "Synthetic event stream for a freemium skilling app -- see the README for how it is "
        "generated and why the numbers are not real-world benchmarks."
    )

    database = st.sidebar.text_input("Warehouse", str(warehouse.DEFAULT_DB))
    con = _connection(database)

    channels = st.sidebar.multiselect("Channel", warehouse.distinct_values(con, "channel"))
    platforms = st.sidebar.multiselect("Platform", warehouse.distinct_values(con, "platform"))
    filters = _encode({"channel": channels, "platform": platforms})

    st.sidebar.divider()
    period = st.sidebar.selectbox("Cohort period", cohorts.PERIODS)
    max_periods = st.sidebar.slider("Periods to show", 2, 15, 8)
    activity = st.sidebar.selectbox(
        "Retention activity event", ["lesson_start", "lesson_complete", "quiz_pass"]
    )

    st.sidebar.divider()
    window = st.sidebar.slider("Conversion window (hours)", 1, 24 * 30, 24 * 7, step=12)
    anchor = st.sidebar.radio("Window measured from", funnels.WINDOW_ANCHORS)
    show_naive = st.sidebar.checkbox("Overlay naive ever-fired funnel", value=True)

    ordered = _funnel(database, float(window), anchor, filters, naive=False)
    long = _retention(database, period, activity, max_periods, filters)

    entered = int(ordered["users"].iloc[0])
    converted = int(ordered["users"].iloc[-1])
    columns = st.columns(4)
    columns[0].metric("Users entering funnel", f"{entered:,}")
    columns[1].metric(f"Reached {ordered['step_name'].iloc[-1]}", f"{converted:,}")
    columns[2].metric("End-to-end conversion", f"{(converted / entered if entered else 0):.2%}")
    if not long.empty:
        curve = cohorts.blended_curve(long)
        week1 = curve[curve["period_index"] == 1]
        if not week1.empty:
            columns[3].metric(f"{period.title()} 1 retention", f"{week1['retention'].iloc[0]:.1%}")

    st.subheader("Funnel")
    figure = go.Figure()
    figure.add_bar(
        x=ordered["step_name"], y=ordered["users"], name=f"Step-ordered ({window}h, {anchor})"
    )
    if show_naive:
        naive = _funnel(database, float(window), anchor, filters, naive=True)
        figure.add_bar(x=naive["step_name"], y=naive["users"], name="Naive (ever fired)")
    figure.update_layout(barmode="group", height=380, margin=dict(t=20, b=20))
    st.plotly_chart(figure, use_container_width=True)

    display = ordered.copy()
    display["step_conversion"] = display["step_conversion"].map("{:.1%}".format)
    display["overall_conversion"] = display["overall_conversion"].map("{:.1%}".format)
    display["median_hours"] = display["median_hours"].round(1)
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader(f"Retention by {period} cohort")
    if long.empty:
        st.info("No users match these filters.")
        return
    matrix = cohorts.as_matrix(long)
    matrix.index = [str(value)[:10] for value in matrix.index]
    heatmap = px.imshow(
        matrix,
        labels={"x": f"{period}s since signup", "y": "Cohort", "color": "Retention"},
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=".0%",
    )
    heatmap.update_layout(height=460, margin=dict(t=20, b=20))
    st.plotly_chart(heatmap, use_container_width=True)
    st.caption("Blank cells are periods that have not happened yet, not zero retention.")

    curve = cohorts.blended_curve(long)
    line = px.line(curve, x="period_index", y="retention", markers=True)
    line.update_layout(height=320, yaxis_tickformat=".0%", margin=dict(t=20, b=20))
    st.subheader("Blended curve (size-weighted, observed cells only)")
    st.plotly_chart(line, use_container_width=True)

    sizes = long.groupby("cohort_period", as_index=False)["cohort_size"].first()
    sizes["cohort_period"] = sizes["cohort_period"].astype(str).str[:10]
    st.caption("Cohort sizes")
    st.dataframe(
        pd.DataFrame(sizes).rename(columns={"cohort_period": "cohort", "cohort_size": "signups"}),
        use_container_width=True,
        hide_index=True,
    )


main()
