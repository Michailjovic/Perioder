"""Number platform for Perioder (v0.8.0).

A single settable number entity: how many pills (tablets) are physically at
home right now. The admin/cycle owner types in the real count after buying
more; each confirmed dose (`perioder.log_pill_taken` / the "Confirm pill
taken" button) decrements it by one automatically (see storage.py), so it
stays roughly in sync without extra bookkeeping. `perioder.set_pills_in_stock`
exists for the same thing via automation/voice/NFC.

This is deliberately a raw physical tablet count, not a pack/box count -
that's the literal thing the cycle owner and supporters actually want to
know ("how many pills do we have at home"), and it doesn't assume pills are
always bought in fixed-size packs.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up the Perioder number entity for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PillsInStockNumber(entry, data)])


class PillsInStockNumber(NumberEntity):
    """Settable count of pills physically at home."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_min_value = 0
    _attr_native_max_value = 500
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "ks"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._data = data
        self._attr_translation_key = "pills_in_stock"
        self.entity_id = f"number.{slugify(entry.title)}_pills_in_stock"
        self._attr_unique_id = f"{entry.entry_id}_pills_in_stock"
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
    def native_value(self) -> int:
        return self._data.pills_in_stock

    async def async_set_native_value(self, value: float) -> None:
        await self._data.async_set_pills_in_stock(int(value))
        # v0.9.34: re-check/reschedule immediately instead of waiting for
        # the (now much coarser) _HEARTBEAT ceiling - same pattern
        # switch.py/select.py/time.py already use for their own settings.
        if self._data.async_request_reschedule is not None:
            await self._data.async_request_reschedule()
