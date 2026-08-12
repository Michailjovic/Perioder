"""Pure cycle / fertility / PMS math for Perioder.

No Home Assistant imports here on purpose - this module is plain Python so
it can be unit tested without a running HA instance (see tests/).

The fertility/phase formulas are adapted from the calendar-based method
used by the cyclist integration (https://github.com/ringleader/cyclist),
simplified slightly to avoid unassigned "gap" days between phases.
"""
from __future__ import annotations

from datetime import date, timedelta

from .const import (
    FERTILITY_FERTILE,
    FERTILITY_LOW,
    FERTILITY_SAFER,
    PHASE_FOLLICULAR,
    PHASE_LUTEAL,
    PHASE_MENSTRUATION,
    PHASE_OVULATION,
)


def cycle_day(last_period_start: date, today: date) -> int:
    """Return the current 1-based day of the cycle.

    Day 1 is the day the period started. If `today` is somehow before
    `last_period_start` (clock skew, bad manual entry), it's clamped to day 1
    instead of returning a negative/zero day.
    """
    delta = (today - last_period_start).days
    return max(delta, 0) + 1


def is_period_active(day: int, period_duration: int) -> bool:
    """True while the period itself is ongoing."""
    return day <= period_duration


def fertile_window(cycle_length: int) -> tuple[int, int]:
    """Return (start_day, end_day) of the fertile window, 1-based cycle days."""
    start = cycle_length - 18
    end = cycle_length - 11
    return start, end


def ovulation_day_estimate(cycle_length: int) -> int:
    """Informational only - the calendar-based estimate of ovulation day."""
    return cycle_length - 14


def fertility(day: int, cycle_length: int) -> str:
    """Return 'fertile' / 'low' / 'safer' for the given cycle day."""
    start, end = fertile_window(cycle_length)
    low_start, low_end = start - 2, end + 2
    if low_start <= day <= low_end:
        if start <= day <= end:
            return FERTILITY_FERTILE
        return FERTILITY_LOW
    return FERTILITY_SAFER


def phase(day: int, cycle_length: int, period_duration: int) -> str:
    """Return the current cycle phase.

    Simplified vs. a strict "ovulation +-2 days" window: here the whole
    fertile window counts as the ovulation phase, so every cycle day maps
    to exactly one phase with no gaps.
    """
    start, end = fertile_window(cycle_length)
    if day <= period_duration:
        return PHASE_MENSTRUATION
    if day < start:
        return PHASE_FOLLICULAR
    if start <= day <= end:
        return PHASE_OVULATION
    return PHASE_LUTEAL


def next_period_date(last_period_start: date, cycle_length: int, today: date) -> date:
    """Return the next predicted period start date on/after `today`."""
    candidate = last_period_start + timedelta(days=cycle_length)
    while candidate < today:
        candidate += timedelta(days=cycle_length)
    return candidate


def days_until_next_period(last_period_start: date, cycle_length: int, today: date) -> int:
    """Return the number of days until the next predicted period."""
    return (next_period_date(last_period_start, cycle_length, today) - today).days


def fertile_window_dates(last_period_start: date, cycle_length: int) -> tuple[date, date]:
    """Return (start_date, end_date) of the *current* cycle's fertile window
    as real calendar dates, inclusive - `fertile_window()` above only gives
    1-based cycle-day numbers, which is enough for the calendar entity (it
    iterates cycle-by-cycle itself, see calendar.py's
    `_period_and_fertile_blocks()`), but the transition-triggered supporter
    notification (v0.9.29, __init__.py's `_async_check_cycle_notifications()`)
    needs one concrete date to compare against `today` and to key its
    once-per-cycle dedup on. Unlike the contraception pack (which wraps
    forward automatically via modulo, see pill_math.py), the cycle itself
    always advances by the owner logging a fresh `last_period_start` - so
    that value alone already identifies "the current cycle", no wraparound
    math needed here.
    """
    start_day, end_day = fertile_window(cycle_length)
    start = last_period_start + timedelta(days=start_day - 1)
    end = last_period_start + timedelta(days=end_day - 1)
    return start, end


def pms_window(next_start: date, pms_window_days: int) -> tuple[date, date]:
    """Return (start_date, end_date) of the PMS window before `next_start`."""
    start = next_start - timedelta(days=pms_window_days)
    end = next_start - timedelta(days=1)
    return start, end


def is_pms_active(
    today: date,
    next_start: date,
    pms_window_days: int,
    override: bool | None = None,
) -> bool:
    """True if `today` falls in the PMS window, honoring a manual override.

    `override=True` forces active, `override=False` forces inactive,
    `override=None` (default) uses the automatic window.
    """
    if override is not None:
        return override
    if pms_window_days <= 0:
        return False
    start, end = pms_window(next_start, pms_window_days)
    return start <= today <= end
