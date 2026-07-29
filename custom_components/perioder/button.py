"""Button platform for Perioder.

- "Confirm pill taken": one tap logs today's dose, so the dashboard doesn't
  need `perioder.log_pill_taken` for the common case (today, right now).
- One "Log symptom: <x>" button per entry in `const.SYMPTOMS` (M5) - the
  "rychlé akce ... log symptomu" quick action from
  ANALYZA-A-ROADMAP.md section 2.9, logging via the same storage method as
  `perioder.log_symptom`.

The matching services still exist for backdating or automation/voice/NFC
use cases.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN, SYMPTOMS
from .storage import PerioderData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Perioder buttons for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [ConfirmPillTakenButton(entry, data)]
    entities.extend(LogSymptomButton(entry, data, symptom) for symptom in SYMPTOMS)
    async_add_entities(entities)


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


class LogSymptomButton(ButtonEntity):
    """Pressing this logs one symptom (see const.SYMPTOMS) with a timestamp."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: PerioderData, symptom: str) -> None:
        self._data = data
        self._symptom = symptom
        self._attr_translation_key = f"log_symptom_{symptom}"
        self.entity_id = f"button.{slugify(entry.title)}_log_symptom_{symptom}"
        self._attr_unique_id = f"{entry.entry_id}_log_symptom_{symptom}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_press(self) -> None:
        await self._data.async_log_symptom(self._symptom)
