"""Calendar platform for Perioder.

Two `calendar` entities per cycle owner:

- `cycle_calendar` - the detailed one, for the cycle owner only. Combines
  predicted period blocks, predicted fertile-window blocks (both projected
  forward and backward from `last_period_start` to cover whatever range
  Home Assistant queries), predicted contraception pack-pause blocks, and
  individual *logged* pill entries (taken/missed) with the confirmation
  delay vs. `reminder_time` in the description - the "see which dates the
  pill was actually taken, and how delayed" idea from
  ANALYZA-A-ROADMAP.md section 2.1 (added 2026-07-29).
- `shared_calendar` - generic "sensitive period" blocks with no detail
  (no distinction between period/fertile/pause in the label, never any
  pill confirmations), for exporting into a shared family calendar. Which
  block *types* show up at all is controlled by the
  `shared_calendar_categories` setting (ANALYZA-A-ROADMAP.md section 2.7) -
  in this project's admin-controlled model that's still an Options
  Flow/`update_settings` choice, like every other setting (section 2.5).

Deliberately does NOT invent an event for every future/unlogged pill day -
only pack-pause windows (predictable) and pill_log entries that actually
exist in storage are shown, to avoid a wall of one-event-per-day noise.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import cycle_math as cm
from . import pill_math as pm
from .const import (
    DOMAIN,
    SHARED_CALENDAR_FERTILE,
    SHARED_CALENDAR_PAUSE,
    SHARED_CALENDAR_PERIOD,
)
from .settings import get_settings
from .storage import PerioderData

# -- pure event generation, no I/O - shared by both calendar entities --------


def _period_and_fertile_blocks(
    last_start: date,
    cycle_length: int,
    period_duration: int,
    start_date: date,
    end_date: date,
) -> list[tuple[str, CalendarEvent]]:
    """Predicted period + fertile-window blocks covering [start_date, end_date].

    Returns (kind, event) pairs, kind in {"period", "fertile"}, so callers can
    filter and/or relabel per calendar (detailed vs. shared).
    """
    blocks: list[tuple[str, CalendarEvent]] = []
    fertile_start_day, fertile_end_day = cm.fertile_window(cycle_length)

    lower = start_date - timedelta(days=cycle_length)
    first_cycle_start = last_start + timedelta(
        days=((lower - last_start).days // cycle_length) * cycle_length
    )

    cycle_start = first_cycle_start
    while cycle_start <= end_date:
        period_end = cycle_start + timedelta(days=period_duration)
        if period_end > start_date and cycle_start < end_date:
            blocks.append(("period", CalendarEvent(start=cycle_start, end=period_end, summary="Perioda")))

        fertile_start = cycle_start + timedelta(days=fertile_start_day - 1)
        fertile_end = cycle_start + timedelta(days=fertile_end_day)
        if fertile_end > start_date and fertile_start < end_date:
            blocks.append(
                ("fertile", CalendarEvent(start=fertile_start, end=fertile_end, summary="Plodné dny"))
            )

        cycle_start += timedelta(days=cycle_length)

    return blocks


def _pause_blocks(
    pack_start: date,
    pack_size: int,
    pause_days: int,
    start_date: date,
    end_date: date,
) -> list[tuple[str, CalendarEvent]]:
    """Predicted pack-pause (placebo) blocks covering [start_date, end_date]."""
    if pause_days <= 0:
        return []

    blocks: list[tuple[str, CalendarEvent]] = []
    total = pm.pack_cycle_length(pack_size, pause_days)
    lower = start_date - timedelta(days=total)
    first_cycle_start = pack_start + timedelta(days=((lower - pack_start).days // total) * total)

    cycle_start = first_cycle_start
    while cycle_start <= end_date:
        pause_start = cycle_start + timedelta(days=pack_size)
        pause_end = cycle_start + timedelta(days=total)
        if pause_end > start_date and pause_start < end_date:
            blocks.append(
                (
                    "pause",
                    CalendarEvent(start=pause_start, end=pause_end, summary="Pauza balení (bez tablet)"),
                )
            )
        cycle_start += timedelta(days=total)

    return blocks


def _pill_log_events(
    pill_log: dict[str, dict[str, Any]],
    reminder_time: time,
    start_date: date,
    end_date: date,
) -> list[CalendarEvent]:
    """One single-day event per *logged* pill_log entry - never guessed."""
    events: list[CalendarEvent] = []
    for date_str, entry in pill_log.items():
        log_date = date.fromisoformat(date_str)
        if not (start_date <= log_date < end_date):
            continue

        status = entry["status"]
        summary = "💊 Vzato" if status == "taken" else "💊 Vynecháno"
        description = None
        logged_at = entry.get("logged_at")
        if logged_at:
            delay = pm.delay_minutes(datetime.fromisoformat(logged_at), log_date, reminder_time)
            reminder_str = reminder_time.strftime("%H:%M")
            if delay > 0:
                description = f"Potvrzeno {delay} min po připomínce ({reminder_str})."
            elif delay < 0:
                description = f"Potvrzeno {-delay} min před připomínkou ({reminder_str})."
            else:
                description = f"Potvrzeno přesně v čase připomínky ({reminder_str})."

        events.append(
            CalendarEvent(
                start=log_date,
                end=log_date + timedelta(days=1),
                summary=summary,
                description=description,
            )
        )
    return events


def _sort_events(events: list[CalendarEvent]) -> list[CalendarEvent]:
    events.sort(key=lambda e: e.start if isinstance(e.start, date) else e.start.date())
    return events


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder calendars for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PerioderCalendar(entry, data), PerioderSharedCalendar(entry, data)])


class PerioderCalendar(CalendarEntity):
    """Detailed calendar: predicted period/fertile blocks + logged contraception events."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "cycle_calendar"
        self.entity_id = f"calendar.{slugify(entry.title)}_cycle_calendar"
        self._attr_unique_id = f"{entry.entry_id}_cycle_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next event, looked up over roughly the next year."""
        today = date.today()
        events = self._events_between(today, today + timedelta(days=400))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date.date(), end_date.date())

    def _events_between(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        settings = get_settings(self._entry)
        contraception = self._data.contraception

        last_start = self._data.last_period_start
        if last_start is not None:
            events.extend(
                event
                for _kind, event in _period_and_fertile_blocks(
                    last_start, settings["cycle_length"], settings["period_duration"], start_date, end_date
                )
            )

        if contraception["active"] and contraception["pack_start_date"]:
            pack_start = date.fromisoformat(contraception["pack_start_date"])
            events.extend(
                event
                for _kind, event in _pause_blocks(
                    pack_start, settings["pack_size"], settings["pause_days"], start_date, end_date
                )
            )

        reminder_time = time.fromisoformat(settings["reminder_time"])
        events.extend(_pill_log_events(contraception["pill_log"], reminder_time, start_date, end_date))

        return _sort_events(events)


class PerioderSharedCalendar(CalendarEntity):
    """Shared calendar: generic "sensitive period" blocks, no detail, no pill data.

    Only the block *kinds* listed in the `shared_calendar_categories` setting
    show up at all, and every one of them is relabeled to the same generic
    summary with no description - the point is a family/shared calendar
    knowing "something's going on", not what.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "shared_calendar"
        self.entity_id = f"calendar.{slugify(entry.title)}_shared_calendar"
        self._attr_unique_id = f"{entry.entry_id}_shared_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def event(self) -> CalendarEvent | None:
        today = date.today()
        events = self._events_between(today, today + timedelta(days=400))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events_between(start_date.date(), end_date.date())

    def _events_between(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        settings = get_settings(self._entry)
        enabled = set(settings["shared_calendar_categories"])
        blocks: list[tuple[str, CalendarEvent]] = []

        last_start = self._data.last_period_start
        if last_start is not None and (SHARED_CALENDAR_PERIOD in enabled or SHARED_CALENDAR_FERTILE in enabled):
            blocks.extend(
                _period_and_fertile_blocks(
                    last_start, settings["cycle_length"], settings["period_duration"], start_date, end_date
                )
            )

        contraception = self._data.contraception
        if (
            SHARED_CALENDAR_PAUSE in enabled
            and contraception["active"]
            and contraception["pack_start_date"]
        ):
            pack_start = date.fromisoformat(contraception["pack_start_date"])
            blocks.extend(
                _pause_blocks(pack_start, settings["pack_size"], settings["pause_days"], start_date, end_date)
            )

        kind_to_category = {"period": SHARED_CALENDAR_PERIOD, "fertile": SHARED_CALENDAR_FERTILE, "pause": SHARED_CALENDAR_PAUSE}
        events = [
            CalendarEvent(start=event.start, end=event.end, summary="Citlivé období")
            for kind, event in blocks
            if kind_to_category[kind] in enabled
        ]

        return _sort_events(events)
