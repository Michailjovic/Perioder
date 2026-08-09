"""Time platform for Perioder.

One settable `time` entity per cycle owner (v0.9.19): the daily
contraception reminder time. `reminder_time` is a *setting*, not runtime
state (see settings.py) - it normally lives in `entry.options`, editable
only via Config/Options Flow, which only a Home Assistant administrator can
reach. Michael asked for it to also be reachable from the cycle owner's own
dashboard, so she can pick her own reminder time without going through the
admin-only flow every time.

This entity writes straight to `entry.options` via
`hass.config_entries.async_update_entry()` - the exact same place Options
Flow writes to - so whichever UI was used most recently simply wins; there
is no separate "two sources of truth" to reconcile, it's the same setting
reachable from two different places for two different people (Michael via
Configure, the cycle owner via her own dashboard).

Deliberately does NOT go through Options Flow / `OptionsFlowWithReload`:
that reloads the whole config entry (tearing down and recreating every
entity) on every save, which is fine for an admin occasionally tuning
settings but far too disruptive for "I want to nudge my reminder 15 minutes
later" from a dashboard tile. `__init__.py`'s notification scheduler already
reads settings fresh via `get_settings()` on every run - but it only *runs*
at whatever instant it last scheduled itself for (see `_compute_next_check_at()`
in `__init__.py`), which has nothing to do with when this entity gets a new
value. Confirmed live 2026-08-09: changing the reminder time here had no
effect until whatever the scheduler's *previously* computed wake happened to
be, silently dropping same-day changes. So this also calls
`data.async_request_reschedule()` (set up in `__init__.py`) right after
writing the new value, to force an immediate re-check/reschedule instead of
waiting on a stale one.
"""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import CONF_REMINDER_TIME, DOMAIN
from .settings import get_settings
from .storage import PerioderData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder reminder-time entity for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ReminderTimeEntity(entry, data)])


class ReminderTimeEntity(TimeEntity):
    """Settable time: the daily contraception reminder. See module docstring."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:alarm"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "reminder_time"
        self.entity_id = f"time.{slugify(entry.title)}_reminder_time"
        self._attr_unique_id = f"{entry.entry_id}_reminder_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    @property
    def native_value(self) -> time:
        return time.fromisoformat(get_settings(self._entry)[CONF_REMINDER_TIME])

    async def async_set_value(self, value: time) -> None:
        # Same "seed from data if options is still empty" fallback
        # config_flow.py's _ensure_working_copy() uses, so a cycle owner
        # changing this before an admin has ever opened Options Flow still
        # keeps every other already-configured setting intact.
        new_options = dict(self._entry.options) or dict(self._entry.data)
        new_options[CONF_REMINDER_TIME] = value.isoformat()
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()
        if self._data.async_request_reschedule is not None:
            await self._data.async_request_reschedule()
