# Interview Prep — Cohort & Funnel Analytics

---

### Q1. Walk me through the architecture in 90 seconds.

_A:_ A seeded generator writes a user-level event stream — signup, lesson_start,
lesson_complete, quiz_pass, subscribe, with channel and platform — into a DuckDB table.
Two modules query it: `cohorts.py` builds a retention triangle, `funnels.py` builds a
step-ordered funnel with a conversion window. Everything aggregates in SQL; pandas only
ever holds a result set. The CLI, the Streamlit dashboard, and the tests all call the same
two functions, so there is one implementation of each metric rather than three that drift.
Filters are applied inside the base CTE, with column names allowlisted and values bound.

### Q2. Why did you choose a step-ordered funnel over the usual `count(DISTINCT user_id)` per event?

_A:_ Because the usual one is wrong, and I can show by how much. On this dataset the naive
funnel reports 255 users reaching `subscribe` against 112 for the ordered version — 2.3×
the true signup→subscribe conversion (6.17% vs 2.71%). Two causes: 143 referral-code users
subscribed without ever passing a quiz, so they should never have been counted at the final
step, and 720 users started their first lesson outside the 7-day window. The ordered funnel
requires each step to occur strictly after the previous one and inside the window; the
window anchor is configurable because "within 7 days of signup" and "each step follows
quickly on the last" are both legitimate definitions for different products.

### Q3. What's the weakest part of this, and what would break first under load?

_A:_ The data is synthetic — that is the honest weakness, and every number in the README is
a property of my generator, not a benchmark. Technically, the funnel is one self-join per
step, so cost grows with step count times event volume. At 100× it would need
first-event-per-user materialised into a `user_first_events` table so the funnel joins ~4M
user rows instead of scanning the raw events, and past that a single-pass approach over a
per-user ordered event array. The dashboard is also querying the warehouse synchronously on
every filter change; that needs pre-aggregated cubes past a handful of concurrent users.

### Q4. How do you know it works? What did you measure, and against what baseline?

_A:_ 33 tests, and every expected value was hand-computed from four fixture users chosen so
each demonstrates exactly one subtlety — a clean path, a late activator, an out-of-order
user, and a drop-off. That matters: a fixture captured from a first run only proves the
code is unchanged, not that it is right. The baseline is the naive metric itself — the
`compare` command runs both and reports the overcount per step, which is how I know the
ordering rule removes 143 users and the window removes 720. Retention is checked the same
way: a two-cohort fixture where I know the answers are 1/3, 2/3, 0, and NULL.

### Q5. Your week-1 retention dropped from 20.0% to 18.2% for the February cohorts. What happened, and would you escalate it?

_A:_ No — I would explain it. Those three cohorts are the paid campaign: 432/444/457
signups against a ~200 baseline. Split by channel, referral retains at 32.9% and social at
15.4%, and neither moved during the campaign. The blended number fell because the mix
shifted towards paid_search and social, not because the product got worse — a mix effect,
the same shape as Simpson's paradox. The action is on acquisition (channel-level CAC and
payback), not on the product team. The caveat I would state up front: cohorts are ~200
users, so a 1.8pt blended difference is not on its own conclusive — the channel split is
what carries the argument, and per-cohort confidence intervals are on my open-questions
list.

---

## 30-second pitch

Product analytics on a raw event stream: cohort retention and a step-ordered, time-windowed
funnel, both computed in DuckDB SQL and surfaced in a Streamlit dashboard. The point of the
project is that the naive versions of both metrics are wrong in specific, measurable ways —
here the naive funnel overstates signup→subscribe conversion by 2.3×, and zero-filling
unobserved retention cells would have made the newest cohorts look like a churn crisis. It
also catches the mix-shift trap: a paid campaign that drops blended retention while every
individual channel holds steady.
