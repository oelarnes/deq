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
from deq.set_config import DEqConfig

AS_OF = dt.date(2026, 9, 14)


def cfg(end_offset: int | None) -> DEqConfig:
    end_date = None if end_offset is None else AS_OF + dt.timedelta(days=end_offset)
    return DEqConfig(start_date=dt.date(2026, 1, 1), end_date=end_date)


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
