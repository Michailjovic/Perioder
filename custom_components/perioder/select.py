"""Select platform for Perioder.

Two `select` entities per cycle owner:

- PMS override (auto / active / inactive) - no external helper/script
  needed. `perioder.set_pms_override` still exists as a service for
  automations, and calls the same underlying storage method.
- `notification_intensity` (v0.9.20): how pushy the daily reminder +
  escalation should be (quiet/normal/urgent/critical - see const.py and
  notifications.py). Same "also settable from Alina's own dashboard, not
  just admin Configure" reasoning as `time.py`'s reminder-time entity - and
  the same mechanism: writes straight to `entry.options`, no Options Flow
  reload triggered, whichever UI was used last simply wins.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import CONF_NOTIFICATION_INTENSITY, DOMAIN, NOTIFICATION_INTENSITIES
from .settings import get_settings
from .storage import PerioderData

_OPTIONS = ["auto", "active", "inactive"]
_TO_STORAGE: dict[str, bool | None] = {"auto": None, "active": True, "inactive": False}
_FROM_STORAGE: dict[bool | None, str] = {None: "auto", True: "active", False: "inactive"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Perioder select entities for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PmsOverrideSelect(entry, data), NotificationIntensitySelect(entry, data)])


class PmsOverrideSelect(SelectEntity):
    """auto = automatic window, active = force on, inactive = force off."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_options = _OPTIONS

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "pms_override"
        self.entity_id = f"select.{slugify(entry.title)}_pms_override"
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


class NotificationIntensitySelect(SelectEntity):
    """How pushy the daily reminder + escalation should be. A *setting*
    (see settings.py), not runtime state - reads/writes entry.options
    directly, same as time.py's ReminderTimeEntity (including calling
    `data.async_request_reschedule()` after writing, for the same reason -
    see that entity's module docstring for why it's needed).
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:volume-vibrate"
    _attr_options = NOTIFICATION_INTENSITIES

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = "notification_intensity"
        self.entity_id = f"select.{slugify(entry.title)}_notification_intensity"
        self._attr_unique_id = f"{entry.entry_id}_notification_intensity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    @property
    def current_option(self) -> str:
        return get_settings(self._entry)[CONF_NOTIFICATION_INTENSITY]

    async def async_select_option(self, option: str) -> None:
        new_options = dict(self._entry.options) or dict(self._entry.data)
        new_options[CONF_NOTIFICATION_INTENSITY] = option
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.async_write_ha_state()
        if self._data.async_request_reschedule is not None:
            await self._data.async_request_reschedule()
