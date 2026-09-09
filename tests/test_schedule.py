"""Nightly-schedule tests.

A wrong schedule fails silently: nobody notices until someone asks about
a document that has been on the share for a week. The previous version
computed this in a shell one-liner inside a YAML folded scalar, which is
three quoting layers and a GNU-specific `date` flag deep.
"""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer.__main__ import seconds_until  # noqa: E402


class TestSecondsUntil:
    def test_later_today(self):
        assert seconds_until("02:00", datetime(2026, 9, 9, 1, 0)) == 3600

    def test_rolls_over_to_tomorrow(self):
        # The common case: the container starts during the working day and
        # the next run is the following night.
        assert seconds_until("02:00", datetime(2026, 9, 9, 13, 0)) == 13 * 3600

    def test_exactly_now_waits_a_full_day_rather_than_looping(self):
        # Returning 0 here would spin: finish a run at 02:00:00, sleep 0,
        # run again immediately, forever.
        assert seconds_until("02:00", datetime(2026, 9, 9, 2, 0)) == 24 * 3600

    def test_one_minute_past_waits_almost_a_day(self):
        assert seconds_until("02:00", datetime(2026, 9, 9, 2, 1)) == 24 * 3600 - 60

    def test_never_returns_zero(self):
        for hour in range(24):
            for minute in (0, 30, 59):
                assert seconds_until("02:00", datetime(2026, 9, 9, hour, minute)) >= 1

    @pytest.mark.parametrize("target,expected_hour", [("00:00", 0), ("23:30", 23)])
    def test_accepts_any_hour(self, target, expected_hour):
        delay = seconds_until(target, datetime(2026, 9, 9, 12, 0))
        landing = (12 * 3600 + delay) // 3600 % 24
        assert landing == expected_hour
