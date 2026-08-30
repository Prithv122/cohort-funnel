from __future__ import annotations

from collections import Counter, defaultdict

from cohortfunnel import events


def test_generation_is_deterministic():
    assert events.generate_events(weeks=4) == events.generate_events(weeks=4)


def test_a_different_seed_gives_a_different_stream():
    assert events.generate_events(seed=1, weeks=4) != events.generate_events(seed=2, weeks=4)


def test_every_event_is_a_known_name_inside_the_window():
    stream = events.generate_events(weeks=6)
    assert {e[2] for e in stream} <= set(events.EVENT_NAMES)
    horizon = events.dt.datetime.combine(
        events.START + events.dt.timedelta(weeks=6), events.dt.time.min
    )
    assert all(e[1] < horizon for e in stream)


def test_every_user_starts_with_a_signup():
    by_user = defaultdict(list)
    for user_id, when, name, _channel, _platform in events.generate_events(weeks=4):
        by_user[user_id].append((when, name))
    assert by_user
    for history in by_user.values():
        assert history == sorted(history)
        assert history[0][1] == events.SIGNUP
        assert sum(1 for _, name in history if name == events.SIGNUP) == 1


def test_the_campaign_weeks_really_are_bigger():
    quiet = events._signups_in_week(5)
    campaign = events._signups_in_week(6)
    assert campaign > quiet * 1.9


def test_the_stream_contains_the_two_anomalies_the_analysis_is_built_around():
    """Late activators and funnel-skipping subscribers must actually be in the data."""
    stream = events.generate_events()
    first = {}
    late_activators = 0
    quiz = set()
    subscribers = set()
    for user_id, when, name, _channel, _platform in stream:
        if name == events.SIGNUP:
            first[user_id] = when
        elif name == events.LESSON_START and user_id not in quiz:
            quiz.add(user_id)  # first lesson_start only
            if (when - first[user_id]).total_seconds() > 7 * 86400:
                late_activators += 1

    passed = {u for u, _, n, _, _ in stream if n == events.QUIZ_PASS}
    subscribers = {u for u, _, n, _, _ in stream if n == events.SUBSCRIBE}
    assert late_activators > 100
    assert len(subscribers - passed) > 50

    names = Counter(e[2] for e in stream)
    assert names[events.SIGNUP] > 2000
    assert names[events.LESSON_START] > names[events.SIGNUP]  # returning users
