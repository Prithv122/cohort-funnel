"""Seeded synthetic event stream for a freemium skilling app.

There is no public dataset with the shape this project needs -- raw user-level events
with signup, activation, and subscription in one stream -- so the events are generated
here. Everything is deterministic: one ``random.Random(SEED)`` drives every draw in a
fixed order, so the same seed reproduces the same warehouse and the same numbers in the
README.

The generator is not noise. Each behaviour below exists so that a *correct* analysis
disagrees with a naive one, which is the whole point of the project:

* **Late activators** -- 12% of users who ever start a lesson do so 3-20 days after
  signup, outside the default 7-day conversion window. A funnel with no window counts
  them; a windowed funnel does not.
* **Out-of-order subscribers** -- some users subscribe straight from a referral code
  without ever passing a quiz. A "did the user ever fire this event" funnel counts them
  at the final step; a step-ordered funnel does not.
* **A paid campaign in weeks 6-8** -- signup volume roughly doubles and the channel mix
  shifts hard towards paid_search and social, whose retention multipliers are the worst
  in the table. The blended retention curve dips for those cohorts while the per-channel
  curves barely move. That is the cohort story the dashboard exists to tell.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

SEED = 20260830

#: Cohort weeks all start on a Monday, so the first signup day is a Monday too.
START = dt.date(2026, 1, 5)
WEEKS = 16
DATA_END = dt.datetime.combine(START + dt.timedelta(weeks=WEEKS), dt.time.min)

SIGNUP = "signup"
LESSON_START = "lesson_start"
LESSON_COMPLETE = "lesson_complete"
QUIZ_PASS = "quiz_pass"
SUBSCRIBE = "subscribe"

#: The product funnel, in intended order.
FUNNEL_STEPS = (SIGNUP, LESSON_START, LESSON_COMPLETE, QUIZ_PASS, SUBSCRIBE)

EVENT_NAMES = FUNNEL_STEPS


@dataclass(frozen=True)
class Channel:
    """Acquisition channel and its multipliers on the baseline probabilities."""

    name: str
    share: float
    activation: float
    conversion: float
    retention: float


CHANNELS = (
    Channel("organic", share=0.34, activation=1.00, conversion=1.00, retention=1.00),
    Channel("paid_search", share=0.31, activation=0.86, conversion=0.71, retention=0.78),
    Channel("referral", share=0.14, activation=1.12, conversion=1.34, retention=1.22),
    Channel("social", share=0.21, activation=0.92, conversion=0.55, retention=0.69),
)

#: Weeks 6-8 inclusive: a paid push that buys volume at the cost of cohort quality.
CAMPAIGN_WEEKS = (6, 7, 8)
CAMPAIGN_SHARES = {"organic": 0.18, "paid_search": 0.52, "referral": 0.06, "social": 0.24}
CAMPAIGN_VOLUME_MULTIPLIER = 2.1

PLATFORMS = (("android", 0.61), ("ios", 0.17), ("web", 0.22))
PLATFORM_CONVERSION = {"android": 0.94, "ios": 1.31, "web": 1.00}

BASE_SIGNUPS_PER_WEEK = 170
WEEKLY_GROWTH = 0.035

P_ACTIVATE = 0.62
P_COMPLETE_GIVEN_START = 0.71
P_QUIZ_GIVEN_COMPLETE = 0.58
P_SUBSCRIBE_GIVEN_QUIZ = 0.21

P_LATE_ACTIVATION = 0.12

#: Probability that a *referral* user subscribes without touching the funnel at all.
P_REFERRAL_DIRECT_SUBSCRIBE = 0.28

P_RETURN_BASE_FREE = 0.18
P_RETURN_BASE_SUBSCRIBER = 0.34
RETENTION_DECAY = 0.82

#: (user_id, event_ts, event_name, channel, platform)
Event = tuple[str, dt.datetime, str, str, str]


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    roll = rng.random() * sum(weight for _, weight in weighted)
    upto = 0.0
    for name, weight in weighted:
        upto += weight
        if roll <= upto:
            return name
    return weighted[-1][0]


def _clamp(p: float) -> float:
    return min(0.98, max(0.0, p))


def _signups_in_week(week: int) -> int:
    volume = BASE_SIGNUPS_PER_WEEK * (1 + WEEKLY_GROWTH * week)
    if week in CAMPAIGN_WEEKS:
        volume *= CAMPAIGN_VOLUME_MULTIPLIER
    return round(volume)


def _channel_mix(week: int) -> list[tuple[str, float]]:
    if week in CAMPAIGN_WEEKS:
        return [(c.name, CAMPAIGN_SHARES[c.name]) for c in CHANNELS]
    return [(c.name, c.share) for c in CHANNELS]


def generate_events(seed: int = SEED, weeks: int = WEEKS) -> list[Event]:
    """Return the full event stream, ordered by (user_id, event_ts).

    Events past the end of the reporting window are dropped rather than clipped. A
    warehouse window ends somewhere, and the retention code has to cope with cohorts
    whose later periods have simply not happened yet.
    """
    rng = random.Random(seed)
    by_name = {c.name: c for c in CHANNELS}
    data_end = dt.datetime.combine(START + dt.timedelta(weeks=weeks), dt.time.min)
    events: list[Event] = []
    user_seq = 0

    for week in range(weeks):
        week_start = START + dt.timedelta(weeks=week)
        mix = _channel_mix(week)
        for _ in range(_signups_in_week(week)):
            user_seq += 1
            user_id = f"u{user_seq:06d}"
            channel = by_name[_pick(rng, mix)]
            platform = _pick(rng, list(PLATFORMS))
            day = week_start + dt.timedelta(days=rng.randrange(7))
            signup_ts = dt.datetime.combine(day, dt.time.min) + dt.timedelta(
                seconds=rng.randrange(86400)
            )

            emitted: list[Event] = []

            # Every free variable is bound as a default: the closure is redefined each
            # iteration, and late binding would otherwise make every call write the last
            # user in the loop.
            def emit(
                name: str,
                ts: dt.datetime,
                _u=user_id,
                _c=channel,
                _p=platform,
                _out=emitted,
            ) -> None:
                if ts < data_end:
                    _out.append((_u, ts, name, _c.name, _p))

            emit(SIGNUP, signup_ts)

            subscribed = False
            if rng.random() < _clamp(P_ACTIVATE * channel.activation):
                if rng.random() < P_LATE_ACTIVATION:
                    delay = dt.timedelta(days=3 + rng.random() * 17)
                else:
                    delay = dt.timedelta(hours=rng.expovariate(1 / 6.0))
                start_ts = signup_ts + delay
                emit(LESSON_START, start_ts)

                conv = channel.conversion * PLATFORM_CONVERSION[platform]
                if rng.random() < _clamp(P_COMPLETE_GIVEN_START * conv):
                    complete_ts = start_ts + dt.timedelta(minutes=rng.expovariate(1 / 40.0))
                    emit(LESSON_COMPLETE, complete_ts)

                    if rng.random() < _clamp(P_QUIZ_GIVEN_COMPLETE * conv):
                        quiz_ts = complete_ts + dt.timedelta(days=rng.expovariate(1 / 2.0))
                        emit(QUIZ_PASS, quiz_ts)

                        if rng.random() < _clamp(P_SUBSCRIBE_GIVEN_QUIZ * conv):
                            emit(SUBSCRIBE, quiz_ts + dt.timedelta(days=rng.expovariate(1 / 3.0)))
                            subscribed = True

            # A referral code lets a user subscribe without touching the funnel at all.
            if (
                not subscribed
                and channel.name == "referral"
                and rng.random() < P_REFERRAL_DIRECT_SUBSCRIBE
            ):
                emit(SUBSCRIBE, signup_ts + dt.timedelta(days=rng.expovariate(1 / 1.0)))
                subscribed = True

            base_return = P_RETURN_BASE_SUBSCRIBER if subscribed else P_RETURN_BASE_FREE
            for k in range(1, weeks - week + 1):
                p_return = _clamp(base_return * channel.retention * RETENTION_DECAY ** (k - 1))
                if rng.random() >= p_return:
                    continue
                return_week_start = dt.datetime.combine(
                    week_start + dt.timedelta(weeks=k), dt.time.min
                )
                for _ in range(rng.randint(1, 4)):
                    emit(
                        LESSON_START,
                        return_week_start + dt.timedelta(seconds=rng.randrange(7 * 86400)),
                    )

            events.extend(emitted)

    events.sort(key=lambda e: (e[0], e[1]))
    return events
