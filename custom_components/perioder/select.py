"""Select platform for Perioder.

A single `select` entity per cycle owner for the manual PMS override
(auto / active / inactive) - no external helper/script needed.
`perioder.set_pms_override` still exists as a service for automations, and
calls the same underlying storage method.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .storage import PerioderData

_OPTIONS = ["auto", "active", "inactive"]
_TO_STORAGE: dict[str, bool | None] = {"auto": None, "active": True, "inactive": False}
_FROM_STORAGE: dict[bool | None, str] = {None: "auto", True: "active", False: "inactive"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder PMS override select for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PmsOverrideSelect(entry, data)])


class PmsOverrideSelect(SelectEntity):
    """auto = automatic window, active = force on, inactive = force off."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_options = _OPTIONS

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "pms_override"
        self.entity_id = "select.pms_override"
        self._attr_unique_id = f"{entry.entry_id}_pms_override"
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
    def current_option(self) -> str:
        return _FROM_STORAGE[self._data.pms_override]

    async def async_select_option(self, option: str) -> None:
        await self._data.async_set_pms_override(_TO_STORAGE[option])
