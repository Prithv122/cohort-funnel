# Resume Bullets — Cohort & Funnel Analytics

---

## Bullets

- Built a product-analytics toolkit over a 15k-event DuckDB warehouse computing weekly
  cohort retention and step-ordered, time-windowed funnels entirely in SQL; demonstrated
  that the conventional "ever fired this event" funnel overstates signup→subscribe
  conversion by 2.3× (6.17% vs 2.71%) by counting 143 out-of-order and 720 out-of-window
  users.
- Shipped a Streamlit/Plotly dashboard on the same metric functions used by the CLI and the
  33-test suite (expectations hand-computed, not captured), surfacing a mix-shift finding a
  blended chart hides: a 2.1× paid campaign cut blended week-1 retention from 20.0% to
  18.2% while every individual channel's curve (referral 32.9% → social 15.4%) held steady.

## Which roles this supports

- [x] Data Scientist / ML
- [ ] AI Engineer (LLM/NLP/CV)
- [x] Data Engineer
- [x] Data Analyst / Python Developer

## Keywords this project earns

DuckDB · analytical SQL (CTE chains, window/date functions, `date_trunc`/`date_diff`) ·
cohort retention · funnel analysis · conversion windows · product analytics · Streamlit ·
Plotly · pandas · pytest · deterministic synthetic data · SQL parameter binding and
column allowlisting · mix effects / Simpson's paradox

---

_Note to self: lead with the 2.3× number. It is the one that makes an interviewer ask "how
did you know?", which is the question this project is built to answer._
