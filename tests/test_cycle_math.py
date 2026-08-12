"""Unit tests for cycle_math.py - pure functions, no Home Assistant needed.

Covers a 28-day reference cycle day-by-day (every day 1-28 must map to
exactly one phase, no gaps - see cycle_math.py's own docstring for why),
plus the edge cases from ANALYZA-A-ROADMAP.md section M7: backdating,
future dates, and the PMS override persisting/resetting correctly.
"""
from __future__ import annotations

from datetime import date, timedelta

from custom_components.perioder import cycle_math as cm

CYCLE_LENGTH = 28
PERIOD_DURATION = 5


def test_cycle_day_basic() -> None:
    start = date(2026, 7, 1)
    assert cm.cycle_day(start, date(2026, 7, 1)) == 1
    assert cm.cycle_day(start, date(2026, 7, 2)) == 2
    assert cm.cycle_day(start, date(2026, 7, 28)) == 28


def test_cycle_day_clamps_before_start() -> None:
    """Clock skew / bad manual entry: today before last_period_start -> day 1, not negative."""
    start = date(2026, 7, 10)
    assert cm.cycle_day(start, date(2026, 7, 1)) == 1


def test_is_period_active() -> None:
    assert cm.is_period_active(1, PERIOD_DURATION) is True
    assert cm.is_period_active(5, PERIOD_DURATION) is True
    assert cm.is_period_active(6, PERIOD_DURATION) is False


def test_every_cycle_day_has_exactly_one_phase() -> None:
    """No gaps: every 1..cycle_length day must map to exactly one phase."""
    seen = set()
    for day in range(1, CYCLE_LENGTH + 1):
        phase = cm.phase(day, CYCLE_LENGTH, PERIOD_DURATION)
        assert phase in {"menstruation", "follicular", "ovulation", "luteal"}
        seen.add(phase)
    assert seen == {"menstruation", "follicular", "ovulation", "luteal"}


def test_phase_menstruation_matches_period_duration() -> None:
    for day in range(1, PERIOD_DURATION + 1):
        assert cm.phase(day, CYCLE_LENGTH, PERIOD_DURATION) == "menstruation"
    assert cm.phase(PERIOD_DURATION + 1, CYCLE_LENGTH, PERIOD_DURATION) != "menstruation"


def test_fertility_levels_present() -> None:
    levels = {cm.fertility(day, CYCLE_LENGTH) for day in range(1, CYCLE_LENGTH + 1)}
    assert levels == {"fertile", "low", "safer"}


def test_fertile_window_matches_phase_ovulation() -> None:
    """fertility()=='fertile' should line up with phase()=='ovulation' (same window)."""
    start, end = cm.fertile_window(CYCLE_LENGTH)
    for day in range(start, end + 1):
        assert cm.phase(day, CYCLE_LENGTH, PERIOD_DURATION) == "ovulation"
        assert cm.fertility(day, CYCLE_LENGTH) == "fertile"


def test_next_period_date_forward() -> None:
    last_start = date(2026, 7, 1)
    assert cm.next_period_date(last_start, CYCLE_LENGTH, date(2026, 7, 1)) == date(2026, 7, 29)
    assert cm.next_period_date(last_start, CYCLE_LENGTH, date(2026, 7, 29)) == date(2026, 7, 29)
    assert cm.next_period_date(last_start, CYCLE_LENGTH, date(2026, 7, 30)) == date(2026, 8, 26)


def test_days_until_next_period() -> None:
    last_start = date(2026, 7, 1)
    assert cm.days_until_next_period(last_start, CYCLE_LENGTH, date(2026, 7, 1)) == 28
    assert cm.days_until_next_period(last_start, CYCLE_LENGTH, date(2026, 7, 29)) == 0


def test_fertile_window_dates_matches_cycle_day_window() -> None:
    """fertile_window_dates() should land on the same days fertile_window()
    (cycle-day numbers) + phase()/fertility() already agree line up with -
    same reference cycle as test_fertile_window_matches_phase_ovulation()."""
    last_start = date(2026, 7, 1)
    start_day, end_day = cm.fertile_window(CYCLE_LENGTH)
    start, end = cm.fertile_window_dates(last_start, CYCLE_LENGTH)
    assert start == last_start + timedelta(days=start_day - 1)
    assert end == last_start + timedelta(days=end_day - 1)
    assert (end - start).days == end_day - start_day


def test_fertile_window_dates_next_cycle_shifts_with_new_period_start() -> None:
    """Unlike the contraception pack's modulo wraparound, the cycle's fertile
    window only ever tracks the *current* logged last_period_start - a new
    period start moves it forward by definition, no separate "current cycle"
    lookup needed (see function docstring)."""
    cycle1_start = date(2026, 7, 1)
    cycle2_start = date(2026, 7, 29)
    start1, _ = cm.fertile_window_dates(cycle1_start, CYCLE_LENGTH)
    start2, _ = cm.fertile_window_dates(cycle2_start, CYCLE_LENGTH)
    assert (start2 - start1).days == CYCLE_LENGTH


def test_pms_window_before_next_period() -> None:
    next_start = date(2026, 7, 29)
    start, end = cm.pms_window(next_start, 4)
    assert start == date(2026, 7, 25)
    assert end == date(2026, 7, 28)


def test_pms_active_automatic() -> None:
    next_start = date(2026, 7, 29)
    assert cm.is_pms_active(date(2026, 7, 26), next_start, 4) is True
    assert cm.is_pms_active(date(2026, 7, 20), next_start, 4) is False


def test_pms_active_zero_window_never_active_without_override() -> None:
    next_start = date(2026, 7, 29)
    assert cm.is_pms_active(date(2026, 7, 28), next_start, 0) is False


def test_pms_override_forces_on_and_off() -> None:
    """A manual override wins regardless of the automatic window - and each
    cycle's override is independent (this function takes the override as a
    plain argument, so "resetting across cycles" is the caller's job of
    passing `None` again - see storage.async_set_pms_override)."""
    next_start = date(2026, 7, 29)
    # Outside the automatic window, but forced on:
    assert cm.is_pms_active(date(2026, 7, 1), next_start, 4, override=True) is True
    # Inside the automatic window, but forced off:
    assert cm.is_pms_active(date(2026, 7, 26), next_start, 4, override=False) is False
    # override=None falls back to automatic:
    assert cm.is_pms_active(date(2026, 7, 26), next_start, 4, override=None) is True
