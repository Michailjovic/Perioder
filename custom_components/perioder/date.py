"""Date platform for Perioder.

Two settable `date` entities per cycle owner:

- `last_period_start`: reading it shows the currently stored last period
  start; setting it *is* the "log period start" action, with backdating
  built in (just pick an earlier date) - no external input_datetime helper
  or script needed. `perioder.log_period_start` still exists as a service
  for automations/voice/NFC use cases, and calls the same underlying
  storage method.
- `last_period_end` (v0.9.0): the real, confirmed last day of the current
  period (inclusive) - optional, and reset back to unset every time a new
  period start is logged (it's a per-cycle fact, see storage.py). Lets the
  calendar show the actual start-to-end span for the period that just
  happened instead of just the `period_duration` estimate. `perioder.log_period_end`
  is the matching service.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN
from .storage import PerioderData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder date entities for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LastPeriodStartDate(entry, data), LastPeriodEndDate(entry, data)])


class LastPeriodStartDate(DateEntity):
    """Settable date: last period start. Setting it logs a new period start."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "last_period_start"
        self.entity_id = f"date.{slugify(entry.title)}_last_period_start"
        self._attr_unique_id = f"{entry.entry_id}_last_period_start"
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
    def native_value(self) -> date | None:
        return self._data.last_period_start

    async def async_set_value(self, value: date) -> None:
        if value > date.today():
            raise ValueError("Cannot log a period start in the future")
        await self._data.async_set_last_period_start(value)


class LastPeriodEndDate(DateEntity):
    """Settable date: the real, confirmed last day of the current period
    (inclusive). Optional - if never set, the calendar just keeps using the
    `period_duration` estimate for the current cycle's block.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "last_period_end"
        self.entity_id = f"date.{slugify(entry.title)}_last_period_end"
        self._attr_unique_id = f"{entry.entry_id}_last_period_end"
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
    def native_value(self) -> date | None:
        return self._data.last_period_end

    async def async_set_value(self, value: date) -> None:
        if value > date.today():
            raise ValueError("Cannot log a period end in the future")
        last_start = self._data.last_period_start
        if last_start is not None and value < last_start:
            raise ValueError("Period end cannot be before its logged start")
        await self._data.async_set_last_period_end(value)
