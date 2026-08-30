# Build Notes — Cohort & Funnel Analytics

Working notes: what broke, what was tried, why X over Y.

---

## Log

### 2026-08-30 — build

- **Started from the metric, not the data.** Wrote the funnel and retention tests against
  hand-built fixture rows *first* (four users, each demonstrating exactly one subtlety:
  clean path, late activator, out-of-order, drop-off), then made them pass. Every expected
  number in `tests/` was worked out on paper. A fixture captured from a first run only
  asserts that the code still does what it did — it cannot catch the code being wrong.
- **Broke:** the funnel CTE chain initially only carried `t{i-1}` forward, so
  `window_from="entry"` had nothing to anchor to from step 2 onwards. Fixed by propagating
  `t0` through every CTE (`GROUP BY 1, 2`).
- **Broke:** `assert math.isnan(...)` on the `active_users` column — DuckDB returns it as a
  nullable integer, so pandas gives `pd.NA`, not `float('nan')`, and `math.isnan` raises
  `TypeError`. Switched to `pd.isna`. The `retention` column *is* float and does give NaN,
  which is why only one of the two assertions failed.
- **Broke:** ruff `B023` on the `emit` closure inside the generator loop — it captured the
  per-user `emitted` list by reference. Harmless today because the closure is called before
  the next iteration, but it is exactly the bug that bites when you later move a call
  outside the loop. Bound every free variable as a default argument.
- **Streamlit + relative imports:** `streamlit run src/cohortfunnel/app.py` executes the
  file as a script with no package context, so `from . import cohorts` raises ImportError.
  Absolute imports work because `uv sync` installs the package into the venv (this is the
  same hatchling-build issue the root `CLAUDE.md` flags for console scripts).

### The generator is the interesting part

Making synthetic data that a *correct* analysis and a *naive* analysis disagree about took
more thought than the SQL. Three planted behaviours:

- 12% of activators start their first lesson 3–20 days after signup → they sit outside the
  default 7-day window (720-user gap at step 1).
- 28% of referral users subscribe straight from a code without passing a quiz → the naive
  funnel counts them at the final step (143-user gap, 2.3× conversion overstatement).
- A weeks 6–8 paid campaign at 2.1× volume with the channel mix shifted to paid_search and
  social → blended week-1 retention drops 20.0% → 18.2% while each channel's own curve
  barely moves.

First attempt at the referral behaviour divided the probability by the channel share,
which made it fire far too often; replaced with a plain per-referral-user probability.

---

## Rejected approaches

| Approach | Why rejected |
|---|---|
| pandas `groupby` for cohorts | The SQL is the transferable artifact — it ports to Postgres/BigQuery nearly unchanged. pandas would also pull the whole event table into memory, which is the habit this project is meant to argue against |
| Zero-filling unobserved retention cells | Makes the newest cohorts look like a churn crisis. NULL is the honest answer |
| Hard-coding the 7-day window | Both anchors are legitimate definitions; a checkout funnel wants `previous`. Made it a parameter and tested both |
| `MATCH_RECOGNIZE`-style single-pass funnel | Right answer at 100× scale, overkill at 15k events, and DuckDB support for it is not there yet. Written up in README §7 instead |
| A real public dataset | Nothing public exposes raw signup + activation + subscription events per user. Would have meant reverse-engineering a funnel out of aggregate data — the opposite of the point |

## Open questions

- [ ] Deploy to Streamlit Community Cloud (needs the Group 3 account) and put the link in the README.
- [ ] Add a consecutive-period retention mode alongside the unbounded one, so the dashboard can show both definitions side by side.
- [ ] Confidence intervals on the per-cohort retention rates — with ~200-user cohorts, a 2pt difference is not obviously signal, and the campaign finding currently leans on the channel split to make its case.
