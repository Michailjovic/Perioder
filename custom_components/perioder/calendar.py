"""Calendar platform for Perioder.

One `calendar` entity per cycle owner, combining three kinds of events over
whatever date range Home Assistant queries:

- predicted period blocks (cycle_math, projected both forward and backward
  from `last_period_start` to cover the query window),
- predicted fertile-window blocks (same cycles),
- contraception pack-pause blocks, plus individual *logged* pill entries
  (taken/missed) with the confirmation delay vs. `reminder_time` in the
  description - the "see which dates the pill was actually taken, and how
  delayed" idea from ANALYZA-A-ROADMAP.md section 2.1 (added 2026-07-29).

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
from .const import DOMAIN
from .settings import get_settings
from .storage import PerioderData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder calendar for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PerioderCalendar(entry, data)])


class PerioderCalendar(CalendarEntity):
    """Predicted period/fertile blocks + logged contraception events."""

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

    # -- event generation (pure, no I/O - safe to call from the sync `event` property) --

    def _events_between(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        settings = get_settings(self._entry)
        contraception = self._data.contraception

        last_start = self._data.last_period_start
        if last_start is not None:
            events.extend(
                self._cycle_blocks(
                    last_start, settings["cycle_length"], settings["period_duration"], start_date, end_date
                )
            )

        if contraception["active"] and contraception["pack_start_date"]:
            pack_start = date.fromisoformat(contraception["pack_start_date"])
            events.extend(
                self._pause_blocks(
                    pack_start, settings["pack_size"], settings["pause_days"], start_date, end_date
                )
            )

        reminder_time = time.fromisoformat(settings["reminder_time"])
        events.extend(
            self._pill_log_events(contraception["pill_log"], reminder_time, start_date, end_date)
        )

        events.sort(key=lambda e: e.start if isinstance(e.start, date) else e.start.date())
        return events

    def _cycle_blocks(
        self,
        last_start: date,
        cycle_length: int,
        period_duration: int,
        start_date: date,
        end_date: date,
    ) -> list[CalendarEvent]:
        """Predicted period + fertile-window blocks covering [start_date, end_date]."""
        events: list[CalendarEvent] = []
        fertile_start_day, fertile_end_day = cm.fertile_window(cycle_length)

        lower = start_date - timedelta(days=cycle_length)
        first_cycle_start = last_start + timedelta(days=((lower - last_start).days // cycle_length) * cycle_length)

        cycle_start = first_cycle_start
        while cycle_start <= end_date:
            period_end = cycle_start + timedelta(days=period_duration)
            if period_end > start_date and cycle_start < end_date:
                events.append(CalendarEvent(start=cycle_start, end=period_end, summary="Perioda"))

            fertile_start = cycle_start + timedelta(days=fertile_start_day - 1)
            fertile_end = cycle_start + timedelta(days=fertile_end_day)
            if fertile_end > start_date and fertile_start < end_date:
                events.append(
                    CalendarEvent(start=fertile_start, end=fertile_end, summary="Plodné dny")
                )

            cycle_start += timedelta(days=cycle_length)

        return events

    def _pause_blocks(
        self,
        pack_start: date,
        pack_size: int,
        pause_days: int,
        start_date: date,
        end_date: date,
    ) -> list[CalendarEvent]:
        """Predicted pack-pause (placebo) blocks covering [start_date, end_date]."""
        if pause_days <= 0:
            return []

        events: list[CalendarEvent] = []
        total = pm.pack_cycle_length(pack_size, pause_days)
        lower = start_date - timedelta(days=total)
        first_cycle_start = pack_start + timedelta(days=((lower - pack_start).days // total) * total)

        cycle_start = first_cycle_start
        while cycle_start <= end_date:
            pause_start = cycle_start + timedelta(days=pack_size)
            pause_end = cycle_start + timedelta(days=total)
            if pause_end > start_date and pause_start < end_date:
                events.append(
                    CalendarEvent(start=pause_start, end=pause_end, summary="Pauza balení (bez tablet)")
                )
            cycle_start += timedelta(days=total)

        return events

    def _pill_log_events(
        self,
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
