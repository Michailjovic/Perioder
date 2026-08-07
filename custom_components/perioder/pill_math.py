"""Pure contraception pack math for Perioder.

No Home Assistant imports here on purpose - same reasoning as cycle_math.py,
plain Python so it can be unit tested without a running HA instance (see
tests/, M7). `pack_size` + `pause_days` are the actual source of truth for
the math regardless of the `regimen_type` label chosen in Config/Options
Flow - the built-in regimens (21/7, 24/4, continuous) just pre-fill those
two numbers, "custom" lets the admin type them directly (see settings.py).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .const import (
    CONTRACEPTION_INACTIVE,
    CONTRACEPTION_MISSED,
    CONTRACEPTION_PAUSED,
    CONTRACEPTION_PENDING,
    CONTRACEPTION_TAKEN,
)


def pack_cycle_length(pack_size: int, pause_days: int) -> int:
    """Full length in days of one pack+pause cycle."""
    return max(pack_size + pause_days, 1)


def day_in_pack(pack_start_date: date, today: date, pack_size: int, pause_days: int) -> int:
    """Return the current 1-based day within the pack+pause cycle.

    Day 1 is `pack_start_date` itself. Wraps around automatically once a
    full pack+pause cycle has elapsed, so a new pack doesn't need to be
    started manually on schedule (though `perioder.start_new_pack` exists
    for backdating/correcting it, same spirit as `log_period_start`).
    """
    total = pack_cycle_length(pack_size, pause_days)
    delta = (today - pack_start_date).days
    return (delta % total) + 1


def current_pack_start(pack_start_date: date, today: date, pack_size: int, pause_days: int) -> date:
    """Return the start date of the pack+pause cycle `today` currently falls in.

    `pack_start_date` itself never changes once set - the automatic
    week-to-week/pack-to-pack rhythm comes entirely from `day_in_pack()`
    wrapping via modulo, on purpose (see its docstring), so nothing needs to
    be re-pressed/re-started each cycle. But that means `pack_start_date` is
    NOT a safe "which cycle are we in" identifier for anything that needs to
    reset once per repeating cycle (e.g. the "pack running low" notification
    dedup in __init__.py) - it's always the same original date. This returns
    the *current* cycle's own start date instead, advancing in whole
    `pack_size + pause_days` steps from `pack_start_date`, so per-cycle state
    can key off something that actually changes each time around.
    """
    total = pack_cycle_length(pack_size, pause_days)
    delta = (today - pack_start_date).days
    return pack_start_date + timedelta(days=(delta // total) * total)


def is_pill_day(day: int, pack_size: int) -> bool:
    """True on an active-pill day; false on a placebo/pause day."""
    return 1 <= day <= pack_size


def days_until_pack_ends(day: int, pack_size: int) -> int:
    """Days remaining in the active-pill part of the pack (0 on the last pill day)."""
    return max(pack_size - day, 0)


def pill_status(
    *,
    active: bool,
    pack_start_date: date | None,
    today: date,
    pack_size: int,
    pause_days: int,
    pill_log: dict[str, dict[str, str | None]],
    now: datetime,
    reminder_time: time,
    grace_minutes: int = 60,
) -> str:
    """Return today's contraception status for the cycle owner.

    One of: inactive, paused, taken, missed, pending.
    - inactive: contraception tracking is turned off (`active=False`) or no
      pack has ever been started.
    - paused: today falls in the pack's placebo/pause window - nothing to take.
    - taken: today already confirmed via `perioder.log_pill_taken` (or the
      button/date entity that calls the same storage method).
    - missed: today is a pill day, not confirmed, and the reminder time plus
      grace period has already passed.
    - pending: today is a pill day, not confirmed yet, still within the
      grace period after `reminder_time` (or before it).

    `pill_log` entries are `{"status": "taken"|"missed", "logged_at": <isoformat datetime or None>}`
    (see storage.py); `logged_at` isn't used for the status itself, only for
    `delay_minutes()` below.
    """
    if not active or pack_start_date is None:
        return CONTRACEPTION_INACTIVE

    day = day_in_pack(pack_start_date, today, pack_size, pause_days)
    if not is_pill_day(day, pack_size):
        return CONTRACEPTION_PAUSED

    logged = pill_log.get(today.isoformat())
    if logged is not None:
        status = logged["status"]
        if status == "taken":
            return CONTRACEPTION_TAKEN
        if status == "missed":
            return CONTRACEPTION_MISSED

    grace_end = datetime.combine(today, reminder_time) + timedelta(minutes=grace_minutes)
    if now >= grace_end:
        return CONTRACEPTION_MISSED
    return CONTRACEPTION_PENDING


def delay_minutes(logged_at: datetime, log_date: date, reminder_time: time) -> int:
    """Minutes between the daily `reminder_time` and the actual confirmation.

    Positive = confirmed after the reminder (late), negative = before it
    (early/on time). Used to show "how delayed" a confirmed dose was, e.g.
    in the calendar (see ANALYZA-A-ROADMAP.md, section 2.1 - added 2026-07-29).
    """
    reminder_dt = datetime.combine(log_date, reminder_time)
    return round((logged_at - reminder_dt).total_seconds() / 60)
