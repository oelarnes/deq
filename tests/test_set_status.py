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


def test_a_fully_pre_configured_future_set_is_not_live_before_launch():
    """A set whose only run is entirely in the future (start and end both
    already known, e.g. a pre-announced event window) must not read as live
    just because current_run()'s no-run-started-yet fallback happens to carry
    a real, later end_date."""
    not_yet_launched = DEqConfig(
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 9))]
    )
    as_of = dt.date(2026, 9, 23)
    assert not is_live(not_yet_launched, as_of)
    assert not has_pending_data(not_yet_launched, as_of)


# A format that ran once, ended, and has a second run configured ahead of
# time (e.g. a set returning to the Arena queue for a known future window).
RETURNING_FORMAT = DEqConfig(
    runs=[
        Run(dt.date(2024, 4, 16), dt.date(2025, 11, 4)),
        Run(dt.date(2026, 9, 22), dt.date(2026, 9, 29)),
    ]
)


def test_a_future_run_does_not_trigger_live_early():
    """Configuring the next run ahead of time must not flip the format live
    before that run's own start_date arrives."""
    as_of = dt.date(2026, 9, 21)
    assert not is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).end_date == dt.date(2025, 11, 4)


def test_a_future_run_goes_live_automatically_on_its_start_date():
    """No manual edit needed on the day the new run starts."""
    as_of = dt.date(2026, 9, 22)
    assert is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).start_date == as_of


def test_the_run_ends_automatically_on_its_own_end_date():
    as_of = dt.date(2026, 9, 30)
    assert not is_live(RETURNING_FORMAT, as_of)
    assert current_run(RETURNING_FORMAT, as_of).end_date == dt.date(2026, 9, 29)


def test_a_bring_back_run_does_not_reset_window_maturity():
    """A brief reactivation of an already-mature format is de minimis next to
    the bulk of its historical data, so it must not reset _resolve_window's
    wide-window check or displayed coverage start back to a fresh-format
    LAST_TWO_WEEKS bootstrap keyed off the new run's start date."""
    launch_plus_week = dt.date(2024, 4, 16) + dt.timedelta(days=7)
    for as_of in [dt.date(2026, 9, 21), dt.date(2026, 9, 25), dt.date(2026, 9, 30)]:
        time_period, _, display_start, _ = _resolve_window(RETURNING_FORMAT, as_of)
        assert time_period == TimePeriod.ALL_EXCEPT_FIRST_WEEK
        assert display_start == launch_plus_week


def test_contender_only_applies_once_the_contender_queue_has_opened():
    """The Contender Draft queue can open partway through a Premier Draft
    run (e.g. two weeks after launch); 17lands' combined event type isn't
    queryable before that, regardless of which run is currently active."""
    staggered_contender = DEqConfig(
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 9))],
        contender_start=dt.date(2026, 10, 13),
    )
    assert not is_contender(staggered_contender, dt.date(2026, 9, 29))
    assert not is_contender(staggered_contender, dt.date(2026, 10, 12))
    assert is_contender(staggered_contender, dt.date(2026, 10, 13))
    assert is_contender(staggered_contender, dt.date(2026, 11, 9))


def test_contender_defaults_off():
    assert not is_contender(RETURNING_FORMAT, dt.date(2026, 9, 25))


def test_a_reactivated_old_set_does_not_displace_the_current_set(monkeypatch):
    """A bring-back run makes the old set live again, but current_set() picks
    the page default by original launch date, not by which run last started —
    otherwise a week-long OTJ return would knock the actual current set (e.g.
    HOB) off the front page."""
    import deq.main

    monkeypatch.setattr(
        deq.main,
        "config",
        {"NEWSET": DEqConfig(runs=[Run(dt.date(2026, 8, 11))]), "OLDSET": RETURNING_FORMAT},
    )

    as_of = dt.date(2026, 9, 25)
    assert is_live(RETURNING_FORMAT, as_of)
    assert current_set(as_of) == "NEWSET"
