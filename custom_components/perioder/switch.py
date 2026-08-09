"""Switch platform for Perioder.

A single switch per cycle owner: pausing notifications entirely (owner's
daily contraception reminder/escalation, and every supporter category) -
e.g. while on vacation together or otherwise not wanting pings, without
losing any cycle/contraception data or having to remove supporters.
`perioder.pause_notifications` still exists as a service for automations.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up the Perioder pause-notifications switch for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PauseNotificationsSwitch(entry, data)])


class PauseNotificationsSwitch(SwitchEntity):
    """On = notifications paused for this cycle owner."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._data = data
        self._attr_translation_key = "pause_notifications"
        self.entity_id = f"switch.{slugify(entry.title)}_pause_notifications"
        self._attr_unique_id = f"{entry.entry_id}_pause_notifications"
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
    def is_on(self) -> bool:
        return self._data.notifications["paused"]

    async def async_turn_on(self, **kwargs) -> None:
        await self._data.async_set_notifications_paused(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._data.async_set_notifications_paused(False)
        # Unpausing while the previously scheduled wake was computed under
        # "paused" (which skips every contraception-specific candidate in
        # __init__.py's _compute_next_check_at()) would otherwise sit idle
        # until the next plain heartbeat/midnight wake - nudge it right now
        # instead (v0.9.21).
        if self._data.async_request_reschedule is not None:
            await self._data.async_request_reschedule()
