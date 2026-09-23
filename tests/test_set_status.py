"""Tests for the two liveness predicates.

They answer different questions and deliberately differ by a day: `is_live`
asks whether the format is open for play, which is what the dropdown groups
on; `has_pending_data` asks whether 17lands may still hold data we have not
pulled, which is what decides whether DEq fetches or reads the cache.
"""

from __future__ import annotations

import datetime as dt

import pytest

from deq.main import has_pending_data, is_live
from deq.set_config import DEqConfig, Run, current_run

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
