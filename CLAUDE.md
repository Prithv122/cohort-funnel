# Cohort & Funnel Analytics — D2

**Tier:** 2 · **Category:** D - Analytics & data science · **Wave:** 2

Root rules in `../CLAUDE.md` apply. This file is project-specific only — keep it under 40 lines.

## What this is

Cohort retention and step-ordered funnel analysis over a synthetic event stream, in DuckDB
SQL, with a Streamlit dashboard. The argument of the project is that the naive versions of
both metrics are measurably wrong on the same data.

## Stack

Python 3.13 · DuckDB · pandas · Streamlit · Plotly · pytest · ruff · GitHub Actions.
No services, no accounts, no env vars — hence no `.env.example`.

## Acceptance criteria

- [x] Cohort, retention and funnel analysis (CATALOG D2)
- [x] Streamlit dashboard
- [x] Product analytics + business framing — the campaign mix-shift finding
- [x] Deployed to Streamlit Community Cloud (Group 3 account) and linked in the README
- [x] Ship gate passes (`/ship`)

## Project-specific notes

- `uv run cohort-funnel build` writes `data/cohorts.duckdb` (gitignored). Deterministic
  under `SEED = 20260830`; regenerating gives byte-identical numbers.
- The dashboard uses **absolute** imports — `streamlit run` executes the file as a script
  with no package context, so relative imports raise ImportError.
- Local pytest needs `--basetemp=<scratchpad>/pt` (root `CLAUDE.md` → Conventions).
- Test expectations are hand-computed from the fixtures in `tests/conftest.py`. If a test
  fails, suspect the code before suspecting the fixture.
