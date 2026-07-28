"""Date platform for Perioder.

A single settable `date` entity per cycle owner: reading it shows the
currently stored last period start; setting it *is* the "log period start"
action, with backdating built in (just pick an earlier date) - no external
input_datetime helper or script needed. `perioder.log_period_start` still
exists as a service for automations/voice/NFC use cases, and calls the same
underlying storage method.
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
    """Set up the Perioder date entity for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LastPeriodStartDate(entry, data)])


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
