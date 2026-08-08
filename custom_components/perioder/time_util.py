"""Timezone-safe 'now'/'today' helpers.

Home Assistant integrations should never rely on Python's bare
`datetime.now()` or `date.today()` for anything user-facing - those read
the underlying OS/container clock, which frequently differs from Home
Assistant's own configured time zone (Settings > General > Time zone).
A very common real case: HA runs in a Docker container whose OS clock is
UTC regardless of what time zone HA itself is configured for. Every plain
`datetime.now()`/`date.today()` call in this integration was silently
reading that container clock instead - found live 2026-08-08, when the
daily 09:00 contraception reminder never fired because the code's idea of
"now" didn't match the wall clock the 09:00 setting was meant to mean.

`homeassistant.util.dt.now()` is Home Assistant's own always-correct
"current moment in the configured time zone" helper. It returns a
*timezone-aware* datetime, but every stored timestamp and every
`datetime.combine(...)` call elsewhere in this integration is naive (no
tzinfo) local time - mixing aware and naive datetimes raises `TypeError`
on comparison. `local_now()` asks HA for the correct wall-clock moment and
then strips the tzinfo back off, so every existing naive-datetime call
site (storage.py's `.isoformat()` timestamps, `datetime.combine()` in
__init__.py, etc.) keeps working unchanged - just anchored to the right
clock now instead of the container's.
"""
from __future__ import annotations

from datetime import date, datetime

from homeassistant.util import dt as dt_util


def local_now() -> datetime:
    """Home Assistant's configured-timezone 'now', as a naive datetime."""
    return dt_util.now().replace(tzinfo=None)


def local_today() -> date:
    """Home Assistant's configured-timezone 'today'."""
    return local_now().date()
