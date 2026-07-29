"""Button platform for Perioder.

A single one-tap button per cycle owner: "Confirm pill taken" for today,
so the dashboard doesn't need the more general `perioder.log_pill_taken`
service call for the common case (today, right now). The service still
exists for backdating or automation/voice/NFC use cases.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.button import ButtonEntity
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
    """Set up the Perioder pill-confirmation button for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ConfirmPillTakenButton(entry, data)])


class ConfirmPillTakenButton(ButtonEntity):
    """Pressing this logs today's dose as taken."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._data = data
        self._attr_translation_key = "confirm_pill_taken"
        self.entity_id = f"button.{slugify(entry.title)}_confirm_pill_taken"
        self._attr_unique_id = f"{entry.entry_id}_confirm_pill_taken"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_press(self) -> None:
        await self._data.async_log_pill_taken(date.today())
