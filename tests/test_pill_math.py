"""Unit tests for pill_math.py - pure functions, no Home Assistant needed.

Covers the M7 edge cases from ANALYZA-A-ROADMAP.md: changing regimen_type
(pack_size/pause_days) mid-pack, deactivating and reactivating, and
backdating a confirmation. "Reject a future date" isn't tested here because
pill_math.py itself has no such guard by design - that validation lives at
the entity/service layer (date.py's async_set_value, and __init__.py's
log_period_start/log_pill_taken/start_new_pack handlers all raise
ValueError for a future date before ever calling into storage.py).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from custom_components.perioder import pill_math as pm

PACK_SIZE = 21
PAUSE_DAYS = 7


def test_day_in_pack_first_and_last_pill_day() -> None:
    start = date(2026, 7, 1)
    assert pm.day_in_pack(start, date(2026, 7, 1), PACK_SIZE, PAUSE_DAYS) == 1
    assert pm.day_in_pack(start, date(2026, 7, 21), PACK_SIZE, PAUSE_DAYS) == 21


def test_day_in_pack_pause_days() -> None:
    start = date(2026, 7, 1)
    assert pm.day_in_pack(start, date(2026, 7, 22), PACK_SIZE, PAUSE_DAYS) == 22
    assert pm.day_in_pack(start, date(2026, 7, 28), PACK_SIZE, PAUSE_DAYS) == 28


def test_day_in_pack_wraps_to_next_cycle() -> None:
    start = date(2026, 7, 1)
    # 21 + 7 = 28-day full cycle - day 29 should wrap back to day 1.
    assert pm.day_in_pack(start, date(2026, 7, 29), PACK_SIZE, PAUSE_DAYS) == 1


def test_current_pack_start_same_pack() -> None:
    start = date(2026, 7, 1)
    assert pm.current_pack_start(start, date(2026, 7, 1), PACK_SIZE, PAUSE_DAYS) == start
    assert pm.current_pack_start(start, date(2026, 7, 28), PACK_SIZE, PAUSE_DAYS) == start


def test_current_pack_start_advances_once_per_automatic_cycle() -> None:
    """The whole point of day_in_pack() wrapping via modulo is that nobody
    re-presses "start new pack" every cycle - but anything keying a
    once-per-pack dedup off the raw (unchanging) pack_start_date would only
    ever fire for the very first pack. current_pack_start() is what such
    code should key off instead - it advances by a full pack+pause_days
    every time day_in_pack() wraps.
    """
    start = date(2026, 7, 1)
    total = PACK_SIZE + PAUSE_DAYS  # 28

    assert pm.current_pack_start(start, date(2026, 7, total), PACK_SIZE, PAUSE_DAYS) == start
    second_cycle_start = start + timedelta(days=total)
    assert pm.current_pack_start(start, date(2026, 7, total) + timedelta(days=1), PACK_SIZE, PAUSE_DAYS) == (
        second_cycle_start
    )
    third_cycle_start = start + timedelta(days=2 * total)
    assert (
        pm.current_pack_start(start, third_cycle_start + timedelta(days=5), PACK_SIZE, PAUSE_DAYS)
        == third_cycle_start
    )


def test_is_pill_day() -> None:
    assert pm.is_pill_day(1, PACK_SIZE) is True
    assert pm.is_pill_day(21, PACK_SIZE) is True
    assert pm.is_pill_day(22, PACK_SIZE) is False


def test_days_until_pack_ends() -> None:
    assert pm.days_until_pack_ends(1, PACK_SIZE) == 20
    assert pm.days_until_pack_ends(21, PACK_SIZE) == 0
    assert pm.days_until_pack_ends(22, PACK_SIZE) == 0  # already past the pack, never negative


def test_regimen_change_mid_pack_reinterprets_same_pack_start() -> None:
    """Edge case from M7: changing regimen_type (pack_size/pause_days) mid-pack.

    pack_start_date is the only thing stored per pack - pack_size/pause_days
    always come live from current settings (see settings.py), so switching
    from 21/7 to 24/4 immediately reinterprets the *same* pack_start_date
    under the new numbers. This is intentional, not a bug - documented here
    as a regression test so a future change to day_in_pack() can't silently
    break it without a test failing.
    """
    start = date(2026, 7, 1)
    today = date(2026, 7, 22)  # day 22 under 21/7 (a pause day)

    day_under_21_7 = pm.day_in_pack(start, today, 21, 7)
    assert day_under_21_7 == 22
    assert pm.is_pill_day(day_under_21_7, 21) is False  # pause day under the old regimen

    day_under_24_4 = pm.day_in_pack(start, today, 24, 4)
    assert day_under_24_4 == 22
    assert pm.is_pill_day(day_under_24_4, 24) is True  # active pill day under the new regimen


def test_pill_status_inactive_without_pack_start() -> None:
    status = pm.pill_status(
        active=True,
        pack_start_date=None,
        today=date(2026, 7, 5),
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime(2026, 7, 5, 22, 0),
        reminder_time=time(21, 0),
    )
    assert status == "inactive"


def test_pill_status_inactive_when_deactivated() -> None:
    """Edge case from M7: deactivate, then reactivate later.

    Deactivating (active=False) always reports "inactive" regardless of
    pack_start_date or pill_log - reactivating with the *same* pack_start_date
    (storage.py never clears it) resumes counting exactly where the pack
    left off, it doesn't restart the pack.
    """
    start = date(2026, 7, 1)
    today = date(2026, 7, 10)

    deactivated = pm.pill_status(
        active=False,
        pack_start_date=start,
        today=today,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime.combine(today, time(22, 0)),
        reminder_time=time(21, 0),
    )
    assert deactivated == "inactive"

    reactivated = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=today,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime.combine(today, time(20, 0)),  # before reminder_time
        reminder_time=time(21, 0),
    )
    assert reactivated == "pending"
    assert pm.day_in_pack(start, today, PACK_SIZE, PAUSE_DAYS) == 10  # unchanged by the pause


def test_pill_status_paused_on_pause_day() -> None:
    start = date(2026, 7, 1)
    status = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=date(2026, 7, 25),
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime(2026, 7, 25, 23, 0),
        reminder_time=time(21, 0),
    )
    assert status == "paused"


def test_pill_status_pending_then_missed_after_grace() -> None:
    start = date(2026, 7, 1)
    today = date(2026, 7, 5)

    pending = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=today,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime.combine(today, time(21, 30)),
        reminder_time=time(21, 0),
        grace_minutes=60,
    )
    assert pending == "pending"

    missed = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=today,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log={},
        now=datetime.combine(today, time(22, 30)),
        reminder_time=time(21, 0),
        grace_minutes=60,
    )
    assert missed == "missed"


def test_pill_status_backdated_confirmation() -> None:
    """Edge case from M7: backdating - confirming a *past* day, not today."""
    start = date(2026, 7, 1)
    yesterday = date(2026, 7, 4)
    pill_log = {yesterday.isoformat(): {"status": "taken", "logged_at": None}}

    status = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=yesterday,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log=pill_log,
        now=datetime.combine(yesterday, time(23, 0)),
        reminder_time=time(21, 0),
    )
    assert status == "taken"


def test_pill_status_explicit_missed_entry() -> None:
    start = date(2026, 7, 1)
    today = date(2026, 7, 5)
    pill_log = {today.isoformat(): {"status": "missed", "logged_at": None}}

    status = pm.pill_status(
        active=True,
        pack_start_date=start,
        today=today,
        pack_size=PACK_SIZE,
        pause_days=PAUSE_DAYS,
        pill_log=pill_log,
        now=datetime.combine(today, time(10, 0)),  # even before reminder_time
        reminder_time=time(21, 0),
    )
    assert status == "missed"


def test_delay_minutes_late_early_and_on_time() -> None:
    log_date = date(2026, 7, 5)
    reminder_time = time(21, 0)

    late = datetime.combine(log_date, time(21, 10))
    assert pm.delay_minutes(late, log_date, reminder_time) == 10

    early = datetime.combine(log_date, time(20, 45))
    assert pm.delay_minutes(early, log_date, reminder_time) == -15

    on_time = datetime.combine(log_date, time(21, 0))
    assert pm.delay_minutes(on_time, log_date, reminder_time) == 0
