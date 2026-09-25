"""Tests for the two liveness predicates.

They answer different questions and deliberately differ by a day: `is_live`
asks whether the format is open for play, which is what the dropdown groups
on; `has_pending_data` asks whether 17lands may still hold data we have not
pulled, which is what decides whether DEq fetches or reads the cache.
"""

from __future__ import annotations

import datetime as dt

import pytest

from spells import TimePeriod

from deq.main import _resolve_window, current_set, has_pending_data, is_live
from deq.set_config import DEqConfig, Run, current_run, is_contender

AS_OF = dt.date(2026, 9, 14)


def cfg(end_offset: int | None) -> DEqConfig:
    end_date = None if end_offset is None else AS_OF + dt.timedelta(days=end_offset)
    return DEqConfig(runs=[Run(dt.date(2026, 1, 1), end_date)])


@pytest.mark.parametrize("end_offset", [None, 1, 0])
def test_open_formats_are_live(end_offset):
    assert is_live(cfg(end_offset), AS_OF)


@pytest.mark.parametrize("end_offset", [-1, -7])
def test_a_closed_format_is_not_live(end_offset):
    """The dropdown closes a set on its end date: by the next publish the
    changeover has certainly happened."""
    assert not is_live(cfg(end_offset), AS_OF)


@pytest.mark.parametrize("end_offset", [None, 0, -1])
def test_data_is_still_pending_the_day_after_the_changeover(end_offset):
    """A snapshot reflects play through the previous day, so the changeover day
    only lands in a run made the day after end_date."""
    assert has_pending_data(cfg(end_offset), AS_OF)


def test_data_is_settled_two_days_after_the_changeover():
    assert not has_pending_data(cfg(-2), AS_OF)


def test_the_predicates_differ_by_exactly_one_day():
    ended_yesterday = cfg(-1)
    assert not is_live(ended_yesterday, AS_OF)
    assert has_pending_data(ended_yesterday, AS_OF)


def test_a_set_is_not_live_before_launch():
    """Even when its whole run, end date included, is configured in advance."""
    not_yet_launched = DEqConfig(
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 10))]
    )
    as_of = dt.date(2026, 9, 23)
    assert not is_live(not_yet_launched, as_of)
    assert not has_pending_data(not_yet_launched, as_of)


# a set that ran once, then returns for a week configured in advance
RETURNING_FORMAT = DEqConfig(
    runs=[
        Run(dt.date(2024, 4, 16), dt.date(2024, 6, 11)),
        Run(dt.date(2026, 9, 22), dt.date(2026, 9, 29)),
    ]
)


def test_a_future_run_does_not_go_live_early():
    as_of = dt.date(2026, 9, 21)
    assert not is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).end_date == dt.date(2024, 6, 11)


def test_a_future_run_goes_live_on_its_start_date():
    as_of = dt.date(2026, 9, 22)
    assert is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).start_date == as_of


def test_a_later_run_closes_on_its_own_end_date():
    as_of = dt.date(2026, 9, 30)
    assert not is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).end_date == dt.date(2026, 9, 29)


def test_a_later_run_keeps_the_launch_based_window():
    """A week of returning play is small next to the original run's data."""
    launch_plus_week = dt.date(2024, 4, 16) + dt.timedelta(days=7)
    for as_of in [dt.date(2026, 9, 21), dt.date(2026, 9, 25), dt.date(2026, 9, 30)]:
        time_period, _, display_start, _ = _resolve_window(RETURNING_FORMAT, as_of)
        assert time_period == TimePeriod.ALL_EXCEPT_FIRST_WEEK
        assert display_start == launch_plus_week


def test_contender_data_starts_the_day_after_contender_opens():
    staggered_contender = DEqConfig(
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 10))],
        contender_start=dt.date(2026, 10, 13),
    )
    assert not is_contender(staggered_contender, dt.date(2026, 9, 30))
    assert not is_contender(staggered_contender, dt.date(2026, 10, 13))
    assert is_contender(staggered_contender, dt.date(2026, 10, 14))
    assert is_contender(staggered_contender, dt.date(2026, 11, 10))


def test_contender_defaults_off():
    assert not is_contender(RETURNING_FORMAT, dt.date(2026, 9, 25))


NEWSET = DEqConfig(runs=[Run(dt.date(2026, 8, 11), dt.date(2026, 9, 29))])


def test_a_returning_set_does_not_become_the_default(monkeypatch):
    import deq.main

    monkeypatch.setattr(
        deq.main, "config", {"NEWSET": NEWSET, "OLDSET": RETURNING_FORMAT}
    )
    as_of = dt.date(2026, 9, 25)
    assert is_live(RETURNING_FORMAT, as_of)
    assert current_set(as_of) == "NEWSET"


def test_the_newest_set_stays_the_default_after_its_run_closes(monkeypatch):
    """With nothing newer configured, no set is live, but the page still needs a default."""
    import deq.main

    monkeypatch.setattr(
        deq.main, "config", {"NEWSET": NEWSET, "OLDSET": RETURNING_FORMAT}
    )
    as_of = dt.date(2026, 10, 15)
    assert not has_pending_data(NEWSET, as_of)
    assert not has_pending_data(RETURNING_FORMAT, as_of)
    assert current_set(as_of) == "NEWSET"
    time_period, _, _, display_end = _resolve_window(NEWSET, as_of)
    assert time_period == TimePeriod.ALL_EXCEPT_FIRST_WEEK
    assert display_end == dt.date(2026, 9, 29)


def test_a_new_set_has_no_data_on_launch_day(monkeypatch):
    """The previous set stays the default until the new one's first day is posted."""
    import deq.main

    launching = DEqConfig(runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 10))])
    monkeypatch.setattr(deq.main, "config", {"NEWSET": NEWSET, "LAUNCHING": launching})
    launch = dt.date(2026, 9, 29)
    assert not has_pending_data(launching, launch)
    assert current_set(launch) == "NEWSET"
    assert has_pending_data(launching, launch + dt.timedelta(days=1))
    assert current_set(launch + dt.timedelta(days=1)) == "LAUNCHING"
